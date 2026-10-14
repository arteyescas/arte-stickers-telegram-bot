FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
ENV PORT=10000
EXPOSE 10000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
CMD ["python", "bot.py"]
