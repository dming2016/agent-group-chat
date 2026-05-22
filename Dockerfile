FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV AGENTCHAT_HOST=0.0.0.0
ENV AGENTCHAT_PORT=8766

EXPOSE 8766

CMD ["python", "server.py"]
