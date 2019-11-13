FROM python:3

ENV GOROOT=/usr/local/go \
    PATH=/usr/local/go/bin:$PATH

WORKDIR /tmp

RUN wget https://dl.google.com/go/go1.13.3.linux-amd64.tar.gz \
 && tar -xvf go1.13.3.linux-amd64.tar.gz \
 && mv go /usr/local

RUN pip3 install GitPython~=3.0 PyGithub~=1.44 PyYAML~=5.1
COPY merge.py /usr/local/bin/merge

ENTRYPOINT ["/usr/local/bin/merge"]
USER 1001
