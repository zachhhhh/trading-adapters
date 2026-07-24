FROM python:3.13-slim

WORKDIR /app
COPY packages/python-sdk /app/packages/python-sdk
RUN python -m pip install --no-cache-dir /app/packages/python-sdk

ENTRYPOINT ["norynta-adapters"]
CMD ["list"]
