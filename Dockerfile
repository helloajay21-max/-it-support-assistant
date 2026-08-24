FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Initialise the SQLite database with sample data
RUN python data/init_db.py

ENV PORT=8501
EXPOSE 8501

CMD ["bash", "-c", "streamlit run app.py --server.port $PORT --server.address 0.0.0.0"]
