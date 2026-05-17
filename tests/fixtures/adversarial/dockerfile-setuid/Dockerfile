# DELIBERATELY ADVERSARIAL — do not run outside the test harness; do not copy into production.
#
# Adversarial fixture for S5-06 (Phase 2). Sets up a setuid-root binary
# (`/usr/local/bin/su-copy`, a copy of busybox with mode 4755), creates a
# non-root user `appuser` (uid 1000), and runs the binary AS the non-root
# user. The setuid bit *would* elevate the effective UID to 0 under normal
# Linux semantics; `--security-opt=no-new-privileges` prevents that
# elevation. The captured artifact then shows the binary executed as
# uid=1000 — the positive proof that `no-new-privileges` is in effect.
#
# Note on the setuid mechanism: the kernel ignores the setuid bit on shell
# scripts (a historic safety quirk), so the binary MUST be a real ELF
# executable. We copy `/bin/busybox` (already present in alpine) rather than
# committing a binary blob to git — the test harness sees the same logical
# fixture without source-tree binaries.
#
# Expected outcome: `TraceScenarioCompleted`; captured artifact bytes
# contain `uid=1000` (regex `(uid=1000|setuid|operation not permitted|
# permission denied)` matches at least once).
FROM alpine:3.20
RUN cp /bin/busybox /usr/local/bin/su-copy \
 && chmod 4755 /usr/local/bin/su-copy \
 && adduser -D -u 1000 appuser
USER 1000
CMD ["sh", "-c", "/usr/local/bin/su-copy id 1>&2; exit 0"]
