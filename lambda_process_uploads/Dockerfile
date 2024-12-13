# Use the official AWS Lambda Python base image
FROM public.ecr.aws/lambda/python:3.9

# Copy the function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

# Install dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Command can be omitted if your handler is `lambda_function.handler`
CMD ["lambda_function.handler"]