FROM ubuntu:22.04

RUN apt-get update && apt-get install -y wget && rm -rf /var/lib/apt/lists/*

RUN wget -O /usr/local/bin/circom https://github.com/iden3/circom/releases/download/v2.1.6/circom-linux-amd64 && \
    chmod +x /usr/local/bin/circom

WORKDIR /workspace

ENTRYPOINT ["circom"]
