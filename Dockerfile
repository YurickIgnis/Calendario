# Usar una imagen base oficial de Python
FROM python:3.11

# Establecer el directorio de trabajo en el contenedor
WORKDIR /app

# Copiar los archivos requirements.txt al contenedor
COPY requirements.txt ./

# Instalar las dependencias del proyecto
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto de los archivos del proyecto al contenedor
COPY . .

# Comando para ejecutar el script
CMD ["python", "./calendario.py"]
