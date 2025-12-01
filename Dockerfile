# Use an official lightweight Python image
FROM python:3.10-slim

# Set working directory inside the container
WORKDIR /app

# Copy only requirements first (for better build caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project into the container
COPY . .

# Expose port 5000 from the container
EXPOSE 5000

# Run your Flask app
# app.py is in the root in your screenshot, so we call it directly
CMD ["python", "app.py"]
