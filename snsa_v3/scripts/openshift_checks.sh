set -e

NS="${1:-}"
OC="oc"
if [ -n "$NS" ]; then
    OC="oc -n $NS"
fi

PASS=0
FAIL=0

check() {
    LABEL="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  ✅ $LABEL"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $LABEL"
        FAIL=$((FAIL + 1))
    fi
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SNSA — OpenShift Runtime Checks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "▶ Deployment"
check "Deployment exists" $OC get deployment snsa
check "2 replicas ready" sh -c "$OC get deployment snsa -o jsonpath='{.status.readyReplicas}' | grep -q '^2$'"
check "No crash-looping pods" sh -c "! $OC get pods -l app=snsa | grep -q CrashLoop"

echo ""
echo "▶ Service & Route"
check "Service exists" $OC get service snsa
check "Route exists" $OC get route snsa

echo ""
echo "▶ Config"
check "ConfigMap exists" $OC get configmap snsa-config
check "Secret exists" $OC get secret snsa-secret

echo ""
echo "▶ Security (requires a running pod)"
POD=$($OC get pods -l app=snsa -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -n "$POD" ]; then
    check "Pod runs as non-root" sh -c "$OC exec $POD -- id | grep -v 'uid=0(root)'"
    check "Django deploy check" sh -c "$OC exec $POD -- python manage.py check --deploy --fail-level WARNING"
else
    echo "  ⚠ No running pod found — skipping in-pod checks"
fi

echo ""
echo "▶ Health endpoints"
ROUTE_HOST=$($OC get route snsa -o jsonpath='{.spec.host}' 2>/dev/null || true)
if [ -n "$ROUTE_HOST" ]; then
    check "/api/health/live/ → 200" sh -c "curl -sf https://$ROUTE_HOST/api/health/live/ | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'"
    check "/api/health/ready/ → 200 (DB ok)" sh -c "curl -sf https://$ROUTE_HOST/api/health/ready/ | grep -Eq '"db"[[:space:]]*:[[:space:]]*"ok"'"
else
    echo "  ⚠ Could not determine Route host — skipping HTTP checks"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: ✅ $PASS passed  ❌ $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[ "$FAIL" -eq 0 ]
