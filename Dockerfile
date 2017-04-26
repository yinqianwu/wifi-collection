FROM python:3.4.5-alpine

RUN mkdir -p /opt/poller
WORKDIR /opt/poller

RUN mkdir -p /tmp/data /tmp/logs

COPY requirements.txt /opt/poller/requirements.txt
RUN pip install -r requirements.txt

COPY . /opt/poller

ARG GIT_COMMIT_HASH
ENV GIT_COMMIT_HASH=$GIT_COMMIT_HASH

ENTRYPOINT ["python3", "collector/collect_data_rest.py"]
CMD ["--log-directory=", "--log-stdout", "config/prod.yml"]

