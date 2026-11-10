"""Evaluate cross-region inference with the context each resource actually receives."""


def profile_resources(profile):
    profile_arn = profile.get("inferenceProfileArn", "")
    models = [x.get("modelArn", "") for x in profile.get("models", [])]
    resources = [profile_arn] + models
    if (profile.get("status") != "ACTIVE" or not models
            or not profile_arn.startswith("arn:aws:bedrock:")
            or ":inference-profile/" not in profile_arn
            or len(set(resources)) != len(resources)
            or any(not x.startswith("arn:aws:bedrock:") or ":foundation-model/" not in x
                   or not x.split(":")[3] for x in models)):
        raise ValueError("invalid_inference_profile_resources")
    return resources


def simulate_resource(iam, principal_arn, resource, *, via_profile=None):
    region = resource.split(":")[3]
    context = [{"ContextKeyName": "aws:RequestedRegion", "ContextKeyValues": [region],
                "ContextKeyType": "string"}]
    if via_profile:
        context.append({"ContextKeyName": "bedrock:InferenceProfileArn",
                        "ContextKeyValues": [via_profile], "ContextKeyType": "string"})
    response = iam.simulate_principal_policy(
        PolicySourceArn=principal_arn, ActionNames=["bedrock:InvokeModel"],
        ResourceArns=[resource], ContextEntries=context)
    evaluations = [x for x in response.get("EvaluationResults", [])
                   if x.get("EvalActionName") == "bedrock:InvokeModel"
                   and x.get("EvalResourceName") == resource]
    decision, missing = "missingEvaluation", []
    if len(evaluations) == 1:
        evaluation = evaluations[0]
        decision = evaluation.get("EvalDecision", "missingEvaluation")
        missing = evaluation.get("MissingContextValues", [])
        for item in evaluation.get("ResourceSpecificResults", []):
            if item.get("EvalResourceName") == resource:
                if item.get("EvalResourceDecision") != "allowed":
                    decision = item.get("EvalResourceDecision", "missingEvaluation")
                missing += item.get("MissingContextValues", [])
    return {"resource": resource, "requested_region": region,
            "inference_profile_context": via_profile,
            "decision": decision, "missing_context": sorted(set(missing)),
            "allowed": decision == "allowed" and not missing}


def simulate_inference_access(iam, principal_arn, profile):
    resources = profile_resources(profile)
    return [simulate_resource(iam, principal_arn, resource,
                              via_profile=resources[0] if index else None)
            for index, resource in enumerate(resources)]
