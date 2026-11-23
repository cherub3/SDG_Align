# Phase 3 Step 3: container build (Cloud Build)

Labels: VERIFIED = from a command/log in this pass (logs in `reports/evidence/cloudbuild_v1*.log`). Not run: the container itself (no Docker locally, no Cloud Run). So cold start and warm p50/p95 are UNKNOWN until Step 6.

## Result
| Item | Value |
|---|---|
| Build | VERIFIED success, id `7aa94270-4eaf-4ecb-ae6d-29b9176e3958`, region asia-south1, default pool |
| Build duration | VERIFIED 6m11s (build), 6m25s wall incl. upload |
| Image | `asia-south1-docker.pkg.dev/sdg-align-fde/sdg-align/api:v1`, digest `sha256:f1e0b42f4681f6ed8ac3205115abee52b6d7eaeea531f3d5496e05a62542bee6` |
| Image size (compressed, registry) | VERIFIED 733,007,775 bytes (~699 MiB) |
| Dockerfile fixes needed | none: it built unchanged on the first build that actually started |
| Not verified | the image starts, startup checks pass, offline model load works inside it, cold start, latency |

## Attempts (3 submits; only the third started a build)
1. PERMISSION_DENIED on project use (serviceusage). Owner role present; most likely API-enable propagation (INFERRED). Cleared by itself.
2. 403: default compute service account lacked `storage.objects.get` on the source bucket. Cause (VERIFIED, read-only): org policy `iam.automaticIamGrantsForDefaultServiceAccounts` enforced (set on org 349956404327) so that account got no roles, and `cloudbuild.useBuildServiceAccount` is enforced so builds run as it.
3. After the IAM change below: success. No push/logging failure, so the extra roles were NOT added.

## IAM changes made (remove at project end)
| When | Command | Member | Role |
|---|---|---|---|
| 2026-11-23 | `gcloud projects add-iam-policy-binding sdg-align-fde --member=serviceAccount:44714566212-compute@developer.gserviceaccount.com --role=roles/cloudbuild.builds.builder --condition=None` | default compute SA | roles/cloudbuild.builds.builder |

Remove: same command with `remove-iam-policy-binding`.

## Other resources created (remove at project end)
- APIs enabled: cloudbuild.googleapis.com, artifactregistry.googleapis.com (dependencies such as storage were already on).
- Artifact Registry repo `sdg-align` (docker, asia-south1), 733 MB.
- Bucket `gs://sdg-align-fde_cloudbuild` (source tarballs, ~7 MB each, 3 uploads), created by gcloud.

## Cost
Build ran on the default pool (expected inside the free build-minutes allowance, INFERRED, billing not checked). Storage: 733 MB in Artifact Registry is just above the 0.5 GB free tier (INFERRED, ~US$0.02-0.03/month). Check the billing report to confirm.
