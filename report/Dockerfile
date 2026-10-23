# Load test report generator as an AWS Lambda container image.
# Reads the k6 results of a run from S3 and writes report.pdf, metrics.json and ai-analysis.json.

FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY main.py ${LAMBDA_TASK_ROOT}/
COPY reportgen/ ${LAMBDA_TASK_ROOT}/reportgen/
COPY config/ ${LAMBDA_TASK_ROOT}/config/

# matplotlib needs a writable cache folder; in Lambda only /tmp is writable
ENV MPLCONFIGDIR=/tmp/matplotlib

CMD ["main.handler"]
