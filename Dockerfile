FROM python:2.7-alpine
MAINTAINER mroth@khanacademy.org
WORKDIR /app

# add LTS version of nodejs
RUN apk --no-cache add nodejs

# install nodejs packages
COPY package.json .
RUN npm install

# install python packages
COPY requirements.txt .
RUN pip2 install --no-cache-dir --target=vendor/py2 -r requirements.txt

COPY . .
CMD [ "/app/runlint.py", "/src", "-v" ]
