"""Read-only checks for the current stack; never triggers a failure or restore."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path


def recovery_evidence_valid(settings):
    """A sign-off flag cannot substitute for dated, scoped drill results."""
    try:
        report = json.loads(Path(settings["resilience_evidence_path"]).read_text(encoding="utf-8-sig"))
        age = datetime.now(timezone.utc) - datetime.fromisoformat(report["at_utc"])
        return (
            report["status"] == "PASS"
            and timedelta(0) <= age <= timedelta(days=30)
            and report["account"] == settings["account"]
            and report["region"] == settings["region"]
            and report["database_id"] == settings["database_id"]
            and report["release"] == settings["release"]
            and report["image_digest"] == settings["release_image_digest"]
            and report["source_overwritten"] is False
            and 0 <= report["backup_lag_seconds"] <= 900
            and all(
                report["restore"][kind]["application_ready"] is True
                and report["restore"][kind]["tls_verified"] is True
                and report["restore"][kind]["schema_cleaned"] is True
                and 0 < report["restore"][kind]["seconds"] <= 3600
                for kind in ("pitr", "snapshot")
            )
            and all(report["drills"][key]["pass"] is True for key in (
                "api_task_replacement", "database_failover", "redis_failover", "api_rollback"
            ))
            and report["temporary_resources_cleaned"] is True
        )
    except (KeyError, TypeError, ValueError, OSError):
        return False


def evaluate(settings, session, service):
    results = []

    def gate(name, ok):
        results.append({"gate": name, "pass": bool(ok)})

    names = ("database_id", "redis_replication_group_id", "release", "release_image_digest", "resilience_evidence_path")
    if not all(settings.get(name) for name in names):
        gate("resilience_inventory_complete", False)
        return results
    gate("resilience_inventory_complete", True)
    ecs = session.client("ecs")
    task_ids = ecs.list_tasks(cluster=settings["cluster"], serviceName=settings["api_service"], desiredStatus="RUNNING")["taskArns"]
    tasks = ecs.describe_tasks(cluster=settings["cluster"], tasks=task_ids)["tasks"] if task_ids else []
    gate("api_running_in_two_azs", len(tasks) >= 2 and len({t.get("availabilityZone") for t in tasks}) >= 2
         and all(t.get("healthStatus") == "HEALTHY" and t["taskDefinitionArn"] == service["taskDefinition"] for t in tasks))
    breaker = service.get("deploymentConfiguration", {}).get("deploymentCircuitBreaker", {})
    gate("api_circuit_breaker_enabled", breaker.get("enable") and breaker.get("rollback"))
    resource = "service/" + settings["cluster"] + "/" + settings["api_service"]
    scaling = session.client("application-autoscaling")
    targets = scaling.describe_scalable_targets(ServiceNamespace="ecs", ResourceIds=[resource],
                                                ScalableDimension="ecs:service:DesiredCount")["ScalableTargets"]
    gate("api_scaling_limits", len(targets) == 1 and targets[0]["MinCapacity"] >= 2 and
         targets[0]["MinCapacity"] <= targets[0]["MaxCapacity"] <= 4 and
         not any(targets[0].get("SuspendedState", {}).values()))
    policies = scaling.describe_scaling_policies(ServiceNamespace="ecs", ResourceId=resource,
                                                 ScalableDimension="ecs:service:DesiredCount")["ScalingPolicies"]
    gate("api_cpu_target_tracking", any(
        p.get("TargetTrackingScalingPolicyConfiguration", {}).get("PredefinedMetricSpecification", {}).get("PredefinedMetricType") == "ECSServiceAverageCPUUtilization"
        and p["TargetTrackingScalingPolicyConfiguration"]["TargetValue"] == 60 for p in policies))

    database = session.client("rds").describe_db_instances(DBInstanceIdentifier=settings["database_id"])["DBInstances"][0]
    gate("database_multi_az_available", database["DBInstanceStatus"] == "available" and database["MultiAZ"]
         and not database.get("PendingModifiedValues"))
    gate("database_private_encrypted_protected", not database["PubliclyAccessible"] and
         database["StorageEncrypted"] and database["DeletionProtection"] and database["BackupRetentionPeriod"] >= 14)
    point = database.get("LatestRestorableTime")
    gate("database_recent_restore_point", point is not None and timedelta(0) <= datetime.now(timezone.utc) - point <= timedelta(minutes=15))
    cache = session.client("elasticache")
    redis = cache.describe_replication_groups(ReplicationGroupId=settings["redis_replication_group_id"])["ReplicationGroups"][0]
    nodes = [node for group in redis.get("NodeGroups", []) for node in group.get("NodeGroupMembers", [])]
    gate("redis_multi_az_failover_available", redis["Status"] == "available" and redis.get("AutomaticFailover") == "enabled"
         and redis.get("MultiAZ") == "enabled" and len(nodes) >= 2 and len({n.get("PreferredAvailabilityZone") for n in nodes}) >= 2)
    gate("redis_tls_auth_backups", redis.get("TransitEncryptionEnabled") and redis.get("AtRestEncryptionEnabled")
         and redis.get("AuthTokenEnabled") and redis.get("SnapshotRetentionLimit", 0) >= 7)

    ec2 = session.client("ec2")
    legacy_group = settings.get("legacy_alb_security_group_id")
    if legacy_group:
        rules = ec2.describe_security_group_rules(Filters=[{"Name": "group-id", "Values": [legacy_group]}])["SecurityGroupRules"]
        public_rules = [rule for rule in rules if not rule.get("IsEgress")
                        and any(rule.get(key) for key in ("CidrIpv4", "CidrIpv6", "PrefixListId"))]
        gate("legacy_public_origin_ingress_closed", not public_rules)
    else:
        gate("legacy_public_origin_ingress_closed", False)
    subnet_ids = service["networkConfiguration"]["awsvpcConfiguration"]["subnets"]
    subnets = ec2.describe_subnets(SubnetIds=subnet_ids)["Subnets"]
    nat_ids = set()
    routes_ok = len({s["AvailabilityZone"] for s in subnets}) >= 2
    for subnet in subnets:
        tables = ec2.describe_route_tables(Filters=[{"Name": "association.subnet-id", "Values": [subnet["SubnetId"]]}])["RouteTables"]
        route = next((r for t in tables for r in t["Routes"] if r.get("DestinationCidrBlock") == "0.0.0.0/0"), {})
        nat_id = route.get("NatGatewayId")
        if not nat_id:
            routes_ok = False
            continue
        nat = ec2.describe_nat_gateways(NatGatewayIds=[nat_id])["NatGateways"][0]
        nat_subnet = ec2.describe_subnets(SubnetIds=[nat["SubnetId"]])["Subnets"][0]
        routes_ok &= nat["State"] == "available" and nat_subnet["AvailabilityZone"] == subnet["AvailabilityZone"]
        nat_ids.add(nat_id)
    gate("private_subnet_nat_in_each_az", routes_ok and len(nat_ids) >= 2)
    log_groups = settings.get("resilience_log_groups", [])
    gate("retention_inventory_recorded", len(log_groups) >= 5)
    logs = session.client("logs")
    for name in log_groups:
        groups = logs.describe_log_groups(logGroupNamePrefix=name)["logGroups"]
        gate("operational_log_retention", any(g["logGroupName"] == name and g.get("retentionInDays", 0) >= 30 for g in groups))
    alarm_names = ["homewallet-dev-api-gateway-5xx", "homewallet-dev-api-gateway-latency"]
    alarms = session.client("cloudwatch").describe_alarms(AlarmNames=alarm_names)["MetricAlarms"]
    topic = "arn:aws:sns:" + settings["region"] + ":" + settings["account"] + ":homewallet-dev-operations"
    gate("public_api_alarms_enabled", len(alarms) == 2 and all(
        alarm.get("ActionsEnabled") and topic in alarm.get("AlarmActions", [])
        and alarm.get("Namespace") == "AWS/ApiGateway"
        and {d["Name"]: d["Value"] for d in alarm.get("Dimensions", [])} == {"ApiId": settings.get("https_api_id")}
        for alarm in alarms))
    subscriptions = session.client("sns").list_subscriptions_by_topic(TopicArn=topic)["Subscriptions"]
    gate("operations_email_subscription_confirmed", any(
        sub.get("Protocol") == "email" and sub.get("SubscriptionArn", "").startswith("arn:aws:sns:")
        for sub in subscriptions))
    gate("dated_scoped_recovery_drills", recovery_evidence_valid(settings))
    return results
