# Hobart Local Deployment Guide

This guide provides instructions for running the Hobart application locally using Docker. This is designed for users with limited programming knowledge.

## Prerequisites

1.  **Install Docker Desktop**: You must have Docker Desktop installed and running on your computer. You can download it from the official Docker website: [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)

## Step-by-Step Instructions

### 1. Configure Environment Variables

-   In the project directory, find the file named `.env.example`.
-   Make a copy of this file and rename the copy to `.env`.
-   Open the new `.env` file in a text editor.
-   You will see a line that says `GOOGLE_MAPS_API_KEY=''`. You **must** paste your personal Google Maps API key between the single quotes.
-   (Optional) For security, it is recommended to also change the `SECRET_KEY` value to a new random string.
-   Save and close the `.env` file.

### 2. Build and Run the Application

-   Open a terminal or command prompt.
-   Navigate to the Hobart project directory (the same directory where these files are located).
-   Run the following command:

    ```sh
    docker-compose -f docker-compose.local.yml up --build
    ```

-   Docker will now download the necessary images and build the application. This may take several minutes the first time you run it.
-   You will see a lot of log output in your terminal. This is normal.

### 3. Access the Application

-   Once the build is complete and the logs have settled down, open your web browser.
-   Go to the following address: [http://localhost:8000](http://localhost:8000)

The Hobart application should now be running locally on your machine.

## Common Operations

### Stopping the Application

-   To stop the application, go back to your terminal window where it is running and press `Ctrl + C`.

### Restarting the Application

-   To restart the application after it has been stopped, run the following command in the project directory:

    ```sh
    docker-compose -f docker-compose.local.yml up
    ```

    (You don't need the `--build` flag unless you have made changes to the application code.)

### Viewing Logs

-   The application logs are shown live in the terminal where you ran the `up` command.
