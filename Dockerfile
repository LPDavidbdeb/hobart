# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # psycopg2 dependencies
    libpq-dev \
    # other dependencies
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements-postgres.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements-postgres.txt

# Copy the entire project into the container
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose the port the app runs on
EXPOSE 8080

# Run gunicorn when the container launches
CMD ["gunicorn", "--bind", ":8080", "--workers", "2", "Hobart.wsgi:application"]
