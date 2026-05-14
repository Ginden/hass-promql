FROM ghcr.io/home-assistant/home-assistant:stable

# Bake in the component and seed config so `docker run $(docker build -q .)` works
# without any volume mounts. docker-compose overrides /config with a bind mount,
# so the seed is only used in the standalone case.
COPY custom_components/promql /config/custom_components/promql
COPY dev/ha-seed/ /config/
