FROM python:3.12.11-slim-bookworm

WORKDIR /processor

# Pinned Python dependencies, plus the Lambda runtime interface client so the
# same image runs as a container (ECS) or as a Lambda function.
COPY requirements.txt /processor/requirements.txt
RUN pip install --no-cache-dir -r /processor/requirements.txt awslambdaric==2.2.1 simplejson==4.2.0

COPY processor/ /processor/processor/
COPY VERSION /processor/VERSION

ENV PYTHONPATH="/processor" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib

# Build the matplotlib font cache at build time (Lambda's file system is read-only
# outside /tmp), then run as an unprivileged user.
RUN MPLCONFIGDIR=/tmp/matplotlib python3 -c "import matplotlib.pyplot" && chmod -R a+rwX /tmp/matplotlib
USER 1000

# Runs main() once as a container, or serves processor.handler as a Lambda
# function (see processor/entry.py).
ENTRYPOINT ["python3", "-m", "processor.entry"]
