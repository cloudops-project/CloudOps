# Canary and rollback

## Current mechanism

ECS deployment circuit breakers, readiness target health, alarms, exact digest manifests, and recorded prior task definitions are implemented. The workflow restores prior task definitions on failure and never automatically downgrades schema.

A weighted 5%/25%/50%/100% ALB canary is not yet wired into the Terraform module. Until a staging rehearsal adds and verifies dual target groups or ECS CodeDeploy, production promotion must use the circuit-breaker rolling deployment and must not be described as a percentage canary.

## Required canary gates

When weighted canary infrastructure is enabled, observe each 5%, 25%, and 50% stage for at least 10 minutes; observe 100% for at least 20 minutes.

Stop on:

- ALB 5xx above 1% or 5 per minute;
- any sustained readiness failure;
- p95 latency above 1.5 seconds;
- authentication failure rate more than 2x baseline;
- database connections above 80% of the measured limit;
- queue depth above 100 for 5 minutes;
- any dead-letter growth;
- notification failure above 2%;
- missing worker heartbeat for two lease intervals;
- any tenant-isolation/security alarm.

## Rollback rehearsal

1. Deploy a synthetic bad-readiness task to staging.
2. confirm promotion halts and the circuit breaker/automation restores the previous task.
3. verify prior digest, readiness, queue processing, alarms, and smoke tests.
4. retain task/service events, alarm history, and timestamps.
5. verify the database remains on the additive migration head.

Production launch is blocked until this rehearsal and a weighted-canary decision are recorded.
