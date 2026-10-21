# k6 + AWS CLI image for running load tests on ECS Fargate.
# The k6 scripts are not included: they are downloaded from S3 at startup,
# so scenarios can be changed without rebuilding the image.

FROM grafana/k6:0.54.0 AS k6

FROM alpine:3.20
RUN apk add --no-cache aws-cli bash ca-certificates
COPY --from=k6 /usr/bin/k6 /usr/bin/k6
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /work
ENTRYPOINT ["/entrypoint.sh"]
