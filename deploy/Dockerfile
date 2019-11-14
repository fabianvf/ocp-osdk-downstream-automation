FROM python:3

ENV GOROOT=/usr/local/go \
    PATH=/usr/local/go/bin:$PATH \
    HOME=/tmp/merge-bot

WORKDIR ${HOME}

RUN pip3 install --no-cache GitPython~=3.0 PyGithub~=1.44 PyYAML~=5.1 \
 && wget https://dl.google.com/go/go1.13.3.linux-amd64.tar.gz \
 && tar -xvf go1.13.3.linux-amd64.tar.gz \
 && mv go /usr/local \
 && mkdir -p ${HOME} \
 && chmod -R g+rwx ${HOME}

COPY merge.py /usr/local/bin/merge

ENTRYPOINT ["/usr/local/bin/merge"]
USER 1001
