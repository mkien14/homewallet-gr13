"""Attach CloudWatch points to a sanitized D4 run summary."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3


def metric_query(key, namespace, name, dimensions, statistic):
    return {
        "Id": key,
        "MetricStat": {
            "Metric": {
                "Namespace": namespace,
                "MetricName": name,
                "Dimensions": [{"Name": n, "Value": v} for n, v in dimensions.items()],
            },
            "Period": 60,
            "Stat": statistic,
        },
        "ReturnData": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("summary")
    args = parser.parse_args()
    path = Path(args.summary)
    summary = json.loads(path.read_text(encoding="utf-8"))
    load = summary["load"]
    start = datetime.fromisoformat(load["start_utc"]) - timedelta(minutes=5)
    end = datetime.fromisoformat(load["end_utc"]) + timedelta(minutes=5)
    now = datetime.now(timezone.utc)
    if end > now:
        end = now

    queries = []
    for service in ("api", "worker"):
        dims = {"ClusterName": "homewallet", "ServiceName": service}
        for name, stem in (("CPUUtilization", "cpu"), ("MemoryUtilization", "memory")):
            for statistic in ("Average", "Maximum"):
                queries.append(metric_query(
                    f"{service}_{stem}_{statistic.lower()}", "AWS/ECS", name,
                    dims, statistic,
                ))
    alb_dims = {"LoadBalancer": "app/homewallet-dev-alb/5f4ebd537cfd7c12"}
    for name, key in (
        ("HTTPCode_ELB_5XX_Count", "alb_generated_5xx"),
        ("HTTPCode_Target_5XX_Count", "target_generated_5xx"),
        ("RequestCount", "alb_request_count"),
    ):
        queries.append(metric_query(key, "AWS/ApplicationELB", name, alb_dims, "Sum"))
    for queue in ("receipts-queue", "receipts-dlq"):
        for name, key in (
            ("ApproximateNumberOfMessagesVisible", "visible"),
            ("ApproximateNumberOfMessagesNotVisible", "inflight"),
        ):
            queries.append(metric_query(
                f"{queue.replace('-', '_')}_{key}", "AWS/SQS", name,
                {"QueueName": queue}, "Maximum",
            ))

    cw = boto3.client("cloudwatch", region_name="ap-southeast-1")
    results = cw.get_metric_data(
        MetricDataQueries=queries,
        StartTime=start,
        EndTime=end,
        ScanBy="TimestampAscending",
    )["MetricDataResults"]
    metrics = {}
    for item in results:
        points = sorted(zip(item["Timestamps"], item["Values"]))
        metrics[item["Id"]] = [
            {"time_utc": timestamp.isoformat(timespec="seconds"), "value": round(value, 4)}
            for timestamp, value in points
        ]
    summary["cloudwatch"] = {
        "collected_utc": now.isoformat(timespec="seconds"),
        "requested_start_utc": start.isoformat(timespec="seconds"),
        "requested_end_utc": end.isoformat(timespec="seconds"),
        "period_seconds": 60,
        "metrics": metrics,
    }
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    for key, points in metrics.items():
        print(f"{key}: {len(points)} points")


if __name__ == "__main__":
    main()
