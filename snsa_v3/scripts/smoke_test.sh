set -e

IMAGE="${1:-IMAGE_REGISTRY/PROJECT/snsa:TAG}"
CONTAINER="snsa-smoke-$$"
PORT=18000

cleanup() {
    docker stop "$CONTAINER" >/dev/null 2>&1 || true
    docker rm  "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "▶ Starting container: $IMAGE"
docker run -d \
    --name "$CONTAINER" \
    --publish "$PORT:8000" \
    -e DJANGO_SETTINGS_MODULE=SNSA.settings.prod \
    -e DJANGO_SECRET_KEY=smoke-test-only \
    -e DATABASE_URL=sqlite:////tmp/smoke.db \
    -e APIM_BASE_URL=http://localhost:9999 \
    -e APIM_API_KEY=smoke \
    -e DJANGO_ALLOWED_HOSTS=localhost \
    -e TRUSTED_PROXY_CIDRS= \
    "$IMAGE"

echo "▶ Waiting for container to start..."
for i in $(seq 1 20); do
    if curl -sf "http://localhost:$PORT/api/health/live/" >/dev/null 2>&1; then
        echo "  ✅ Container up after ${i}s"
        break
    fi
    sleep 1
    if [ "$i" -eq 20 ]; then
        echo "  ❌ Container did not start in 20s"
        docker logs "$CONTAINER"
        exit 1
    fi
done

echo "▶ Checking /api/health/live/"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/api/health/live/")
if [ "$STATUS" != "200" ]; then
    echo "  ❌ /live/ returned $STATUS"
    exit 1
fi
echo "  ✅ /live/ → 200"

echo "▶ Checking /api/health/ready/"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/api/health/ready/")
if [ "$STATUS" != "200" ]; then
    echo "  ❌ /ready/ returned $STATUS (DB may not be reachable)"
    exit 1
fi
echo "  ✅ /ready/ → 200"

echo "▶ Checking process runs as non-root"
UID_IN_CONTAINER=$(docker exec "$CONTAINER" id -u)
if [ "$UID_IN_CONTAINER" -eq 0 ]; then
    echo "  ❌ Container running as root (UID 0)"
    exit 1
fi
echo "  ✅ Non-root UID: $UID_IN_CONTAINER"

echo ""
echo "✅ All smoke checks passed."
