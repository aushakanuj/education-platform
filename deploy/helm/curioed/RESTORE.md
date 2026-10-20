# Point-in-time restore

Off-site backup is a Barman Cloud `ObjectStore` plus WAL archiving. This chart turns that on with `cnpg.backup.enabled=true`. It does not template a restore. Apply the recovery Cluster below by hand, into a new name, and verify it before any traffic uses it.

The chart template accepts any S3-compatible endpoint. Cloudflare R2 is the store this install uses. The placeholders below are not real account ids, bucket names, or tokens.

## Before you start

- The Barman Cloud plugin is installed in the CloudNativePG operator namespace.
- `cnpg.backup.enabled` was true on the source, and at least one `Backup` completed.
- Secret `curioed-backup-s3` exists in the namespace where the new Cluster will run. Keys are `ACCESS_KEY_ID` and `ACCESS_SECRET_KEY`. Do not commit the Secret.
- You know the source cluster name (`curioed-postgres` for a release named `curioed`) and a UTC timestamp inside the backup window.

```sh
kubectl get scheduledbackup,backup -n curioed
kubectl get objectstore -n curioed
```

WAL archiving is continuous once the source Cluster lists `barman-cloud.cloudnative-pg.io` with `isWALArchiver: true`. Base backups follow `cnpg.backup.schedule` (default `0 0 21 * * *`, 21:00 UTC, 02:30 IST). Retention is `cnpg.backup.retentionPolicy` (default `30d`) on the ObjectStore. A timestamp older than that window cannot be restored.

## Cloudflare R2

R2 speaks the S3 API. Barman does not take a region as a plain string. `s3Credentials.region` is a reference to a key in `curioed-backup-s3`. For R2 that key must contain the literal `auto`.

Use these chart values when you enable backups. Keep the angle brackets until you have the real account id and bucket name, and do not commit either one:

```text
cnpg.backup.endpointURL=https://<account-id>.r2.cloudflarestorage.com
cnpg.backup.bucket=<r2-bucket>
cnpg.backup.path=curioed/postgres
cnpg.backup.regionKey=REGION
```

The recovery Cluster later in this file reads that same ObjectStore, so the Secret has to exist in `curioed` before a restore as well.

### Manual step for the repo owner

Do this before the first backup. Nothing in git or CI creates the bucket, the token, or the Secret.

1. In the Cloudflare dashboard, create an R2 bucket.
2. Create an R2 API token that can read and write only that bucket. Cloudflare shows the access key id and the secret once.
3. Create the Secret from those values. The command below is placeholders only:

```sh
kubectl create secret generic curioed-backup-s3 \
  --namespace curioed \
  --from-literal=ACCESS_KEY_ID='<r2-access-key-id>' \
  --from-literal=ACCESS_SECRET_KEY='<r2-secret-access-key>' \
  --from-literal=REGION='auto'
```

## Restore into a new Cluster

Save this as a local file. Replace the timestamp. Leave the endpoint, bucket, and path as the values from the source install.

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: curioed-postgres-restore
  namespace: curioed
spec:
  instances: 1
  imageName: ghcr.io/cloudnative-pg/postgresql:16.15-standard-bookworm
  imagePullPolicy: IfNotPresent
  bootstrap:
    recovery:
      source: curioed-source
      recoveryTarget:
        targetTime: "2026-10-20 02:00:00.000000+00"
  externalClusters:
    - name: curioed-source
      plugin:
        name: barman-cloud.cloudnative-pg.io
        parameters:
          barmanObjectName: curioed-backup
          serverName: curioed-postgres
  storage:
    size: 20Gi
    storageClass: local-path
```

The ObjectStore `curioed-backup` must already exist in `curioed` (the chart creates it when backups are enabled). `serverName` is the source Cluster name. This manifest does not set `plugins`, so the restored instance does not archive WAL back into the source path.

```sh
kubectl apply -f curioed-postgres-restore.yaml
kubectl get cluster -n curioed -w
```

Wait until `curioed-postgres-restore` reports ready. A drill stops here, then deletes the restore Cluster and its PVC. The application keeps using `curioed-postgres-rw`.

## Verify

```sh
kubectl exec -n curioed curioed-postgres-restore-1 -c postgres -- \
  psql -U postgres -d education -c 'SELECT 1'
kubectl exec -n curioed curioed-postgres-restore-1 -c postgres -- \
  psql -U postgres -d education -c 'SELECT version_num FROM alembic_version'
kubectl exec -n curioed curioed-postgres-restore-1 -c postgres -- \
  psql -U postgres -d education -c \
  'SELECT (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM topics) AS topics, (SELECT count(*) FROM quiz_attempts) AS quiz_attempts'
```

Check that:

- `SELECT 1` returns one row.
- `alembic_version.version_num` is the migration head you expect for that timestamp.
- The three counts are plausible for that time of day. Compare them with a note you took before the incident, or with the last pre-migration `pg_dump` on the backups PVC if the original disk is still readable.
- A known account is present, for example `SELECT email FROM users WHERE email = 'fatima.almansouri@alnoor.school'`.
- The restored cluster has no `isWALArchiver` plugin until you decide it should start its own backup history.

## Serving traffic from the recovered data

The CurioEd chart builds `DATABASE_URL` from the Cluster name `curioed-postgres`. A Helm upgrade of that release always renders `bootstrap.initdb`. CloudNativePG ignores bootstrap changes on a Cluster that already exists, and it will not wipe a healthy cluster. Do not delete the Cluster and then `helm upgrade`: Helm would create an empty database.

For a real failover:

1. Scale the API, web, and worker Deployments to 0.
2. Confirm the restore Cluster passed the checks above.
3. Only if the original Cluster is unusable, delete it and its PVC after you accept that the original disk copy is gone.
4. Apply a recovery Cluster **named `curioed-postgres`** (the chart's name), with the same `externalClusters` block and a `targetTime`. Wait until its `-rw` Service answers.
5. Scale the application back up. It uses the recovered instance because the Service name matches.
6. On the next `helm upgrade`, review the diff. Bootstrap in the chart will not match the live object. That is expected. Confirm Helm is not deleting the Cluster.

Take a new base backup onto a separate prefix before you point WAL archiving at the bucket again. Reusing the source prefix from a recovered primary mixes two histories.
