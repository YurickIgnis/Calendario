import os.path
import datetime as dt
import requests
import time
import datetime
import json


from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Google Calendar scopes
SCOPES_GOOGLE = ['https://www.googleapis.com/auth/calendar']
# Microsoft Graph endpoint
MICROSOFT_GRAPH_ENDPOINT = 'https://graph.microsoft.com/v1.0'
# Microsoft Graph configuration (debes reemplazar estos valores con los tuyos)
CLIENT_ID = '4cc7f037-af02-4744-bdfc-7d98d9498aed'
CLIENT_SECRET = 'rkc8Q~wk7ZCgnLA55FlBXe~Xu0fGMBFaA~uDpave'
TENANT_ID = 'd3e8bd86-c71c-43a1-bf8a-0f3babfe8d82'
AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
TOKEN_ENDPOINT = f'{AUTHORITY}/oauth2/v2.0/token'
SCOPES_MICROSOFT = ['https://graph.microsoft.com/.default']

def get_microsoft_token(force_refresh=False):
    """
    Obtiene un nuevo token de Microsoft Graph.
    Si force_refresh es True, fuerza la obtención de un nuevo token incluso si uno ya existe.
    """
    if force_refresh or not hasattr(get_microsoft_token, 'token'):
        data = {
            'client_id': CLIENT_ID,
            'scope': ' '.join(SCOPES_MICROSOFT),
            'client_secret': CLIENT_SECRET,
            'grant_type': 'client_credentials',
        }
        response = requests.post(TOKEN_ENDPOINT, data=data)
        response_data = response.json()
        get_microsoft_token.token = response_data.get('access_token')
    return get_microsoft_token.token


def convert_millis_to_iso8601(millis):
    """Convierte milisegundos desde la época UNIX a una cadena de fecha y hora en formato ISO 8601."""
    date_time = datetime.datetime.utcfromtimestamp(int(millis) / 1000)
    return date_time.strftime('%Y-%m-%dT%H:%M:%SZ')

def create_outlook_event(token, issue, user_id='usi.rommel.gomez@slp.gob.mx'):
    start_millis = get_custom_field_value(issue, 'Hora de Inicio')
    end_millis = get_custom_field_value(issue, 'Hora de Fin')

    start_time = convert_millis_to_iso8601(start_millis)
    end_time = convert_millis_to_iso8601(end_millis)
    location = get_custom_field_value(issue, 'Ubicacion')
    attendees_emails = get_custom_field_value(issue, 'Invitados').split(',') if get_custom_field_value(issue, 'Invitados') else []
    
    event = {
        "subject": issue['summary'],
        "body": {
            "contentType": "HTML",
            "content": issue['description']
        },
        "start": {
            "dateTime": start_time,
            "timeZone": "UTC"
        },
        "end": {
            "dateTime": end_time,
            "timeZone": "UTC"
        },
        "location": {
            "displayName": location
        },
        "attendees": [{
            "emailAddress": {"address": attendee.strip()},
            "type": "required"
        } for attendee in attendees_emails]
    }

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    event_id = find_outlook_event_by_summary(token, user_id, issue['summary'])
    if event_id:  # Si el evento existe, actualízalo
        url = f"{MICROSOFT_GRAPH_ENDPOINT}/users/{user_id}/calendar/events/{event_id}"
        response = requests.patch(url, headers=headers, json=event)
        print("Evento actualizado en Outlook Calendar.")
    else:  # Si el evento no existe, créalo
        url = f"{MICROSOFT_GRAPH_ENDPOINT}/users/{user_id}/calendar/events"
        response = requests.post(url, headers=headers, json=event)
        print("Evento creado en Outlook Calendar.")
    
    if response.status_code in [200, 201, 204]:  # 204 para actualización exitosa
        print(f"Evento creado o actualizado en Outlook Calendar: {response.json().get('id', 'No ID returned')}")
    else:
        print(f"Error al crear o actualizar el evento en Outlook Calendar: {response.text}")

def find_outlook_event_by_summary(token, user_id, summary):
    headers = {'Authorization': f'Bearer {token}'}
    url = f"{MICROSOFT_GRAPH_ENDPOINT}/users/{user_id}/calendar/events"
    params = {'$filter': f"subject eq '{summary}'"}
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        events = response.json().get('value', [])
        if events:
            return events[0]['id']  # Retorna el ID del primer evento que coincida
    return None


def get_youtrack_issues():
    youtrack_token = "perm:cm9vdA==.NTMtMA==.v59vo5K9N8v1uODB2E69Y4spUMk7xj"
    headers = {'Authorization': 'Bearer ' + youtrack_token}
    url_issues = "https://usi-desarrollo.youtrack.cloud/api/admin/projects/0-45/issues?fields=id,summary,description,customFields($type,id,name,value)"
    response = requests.get(url_issues, headers=headers)
    issues = response.json()
    # print("Respuesta completa de un issue para depuración:", issues[0])  # Imprime solo el primer issue para revisión
    return issues

def convert_millis_to_date(millis, timezone_offset="-06:00"):
    if millis:
        date_time = dt.datetime.fromtimestamp(int(millis) / 1000)
        return date_time.isoformat() + timezone_offset  # Ajustar a la zona horaria
    return None

def get_custom_field_value(issue, field_name):
    for field in issue['customFields']:
        if field['name'] == field_name:
            return field.get('value')
    return None

def get_calendar_field_value(issue):
    print(f"Buscando valor del campo 'Calendario' para el issue: {issue['id']}")  # Depuración para identificar el issue que se está procesando
    return get_custom_field_value(issue, 'Calendario')

def find_event_by_summary(service, summary):
    try:
        events_result = service.events().list(calendarId='primary', q=summary, singleEvents=True).execute()
        for event in events_result.get('items', []):
            if event['summary'] == summary:
                return event['id']
    except HttpError as error:
        print(f"Error al buscar el evento: {error}")
    return None


def update_youtrack_issue_from_google_event(service_google, issue_id, google_event_id):
    """
    Obtiene detalles de un evento de Google Calendar y actualiza el issue correspondiente en YouTrack.
    :param service_google: Cliente de servicio de Google Calendar.
    :param issue_id: ID del issue de YouTrack a actualizar.
    :param google_event_id: ID del evento de Google Calendar.
    """
    try:
        # Obtener detalles del evento de Google Calendar.
        event = service_google.events().get(calendarId='primary', eventId=google_event_id).execute()

        # Extraer campos relevantes.
        summary = event.get('summary', '')
        description = event.get('description', '')
        start_time = event['start'].get('dateTime', '') if 'dateTime' in event['start'] else event['start'].get('date', '')
        end_time = event['end'].get('dateTime', '') if 'dateTime' in event['end'] else event['end'].get('date', '')

        # Actualizar issue en YouTrack.
        update_youtrack_issue(issue_id, {
            'summary': summary,
            'description': description,
            # Agrega aquí más campos si es necesario, como las fechas de inicio y fin.
            'start_time': start_time,
            'end_time': end_time,
        })

    except HttpError as error:
        print(f"Error al obtener el evento de Google Calendar: {error}")

def update_youtrack_issue(issue_id, updated_info):
    """
    Actualiza un issue en YouTrack basado en la información actualizada del evento del calendario.
    :param issue_id: ID del issue de YouTrack a actualizar.
    :param updated_info: Diccionario con la información actualizada del evento.
    """
    youtrack_token = "perm:cm9vdA==.NTMtMA==.v59vo5K9N8v1uODB2E69Y4spUMk7xj"
    headers = {
        'Authorization': 'Bearer ' + youtrack_token,
        'Content-Type': 'application/json',
    }
    url = f"https://usi-desarrollo.youtrack.cloud/api/issues/{issue_id}"
    
    # Asegúrate de mapear correctamente los campos de fecha de inicio y fin a los campos de YouTrack.
    data = {
        "summary": updated_info['summary'],
        "description": updated_info['description'],
        # Aquí necesitarías ajustar la estructura para las fechas de inicio y fin según cómo estén definidos tus campos en YouTrack.
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        print(f"Issue {issue_id} actualizado en YouTrack.")
    else:
        print(f"Error al actualizar el issue en YouTrack: {response.text}")

def save_issues_state(issues, filename='issues_state.json'):
    """Guarda el estado actual de los issues en un archivo JSON."""
    with open(filename, 'w') as file:
        json.dump(issues, file)

def load_issues_state(filename='issues_state.json'):
    """Carga el estado previamente guardado de los issues desde un archivo JSON."""
    try:
        with open(filename, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return []

def get_deleted_issues(previous_issues, current_issues):
    """Determina cuáles issues han sido borrados comparando el estado anterior y actual."""
    previous_ids = {issue['id'] for issue in previous_issues}
    current_ids = {issue['id'] for issue in current_issues}
    deleted_ids = previous_ids - current_ids
    return [issue for issue in previous_issues if issue['id'] in deleted_ids]

def delete_google_event(service_google, google_event_id):
    try:
        service_google.events().delete(calendarId='primary', eventId=google_event_id).execute()
        print(f"Evento borrado en Google Calendar: {google_event_id}")
    except Exception as e:
        print(f"Error al borrar el evento en Google Calendar: {e}")

def delete_outlook_event(token, user_id, outlook_event_id):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/events/{outlook_event_id}"
    response = requests.delete(url, headers=headers)
    if response.status_code in [204, 200]:
        print(f"Evento borrado en Outlook Calendar: {outlook_event_id}")
    else:
        print(f"Error al borrar el evento en Outlook Calendar: {response.text}")


def main_loop(service_google, ms_token):

    last_update_times = {
        "youtrack": {},  # Supongamos que esto está estructurado como {issue_id: last_update_time}
        "google_calendar": {},  # Estructurado como {event_id: last_update_time}
    }
    # creds = None
    # if os.path.exists("token.json"):
    #     creds = Credentials.from_authorized_user_file("token.json", SCOPES_GOOGLE)
    # if not creds or not creds.valid:
    #     if creds and creds.expired and creds.refresh_token:
    #         creds.refresh(Request())
    #     else:
    #         flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES_GOOGLE)
    #         creds = flow.run_local_server(port=0)
    #     with open("token.json", "w") as token:
    #         token.write(creds.to_json())
    while True:
        try:
            # service_google = build("calendar", "v3", credentials=creds)
            # ms_token = get_microsoft_token()

            # Cargar el estado anterior de los issues.
            previous_issues = load_issues_state()

            print (previous_issues)

            # Obtener los issues actuales desde YouTrack.
            current_issues = get_youtrack_issues()

            print (current_issues)

            # Detectar issues borrados.
            deleted_issues = get_deleted_issues(previous_issues, current_issues)

            # Procesar issues borrados para eliminar eventos asociados.
            for issue in deleted_issues:
                # Aquí asumimos que 'issue' contiene un campo 'summary' que usas para encontrar el evento.
                try:
                    google_event_id = find_event_by_summary(service_google, issue['summary'])
                    if google_event_id:
                        delete_google_event(service_google, google_event_id)
                except Exception as e:
                    print(f"No se pudo borrar el evento de Google Calendar: {e}")

                try:
                    outlook_event_id = find_outlook_event_by_summary(ms_token, 'usi.rommel.gomez@slp.gob.mx', issue['summary'])
                    if outlook_event_id:
                        print("hola")
                        delete_outlook_event(ms_token, 'usi.rommel.gomez@slp.gob.mx', outlook_event_id)
                except Exception as e:
                    print(f"No se pudo borrar el evento de Outlook Calendar: {e}")

            # Guardar el estado actual de los issues para la próxima ejecución.
            save_issues_state(current_issues)

            
            issues = get_youtrack_issues()

            for issue in issues:
                # print(issue)
                calendar_value = get_calendar_field_value(issue)  
                print(f"Valor de 'Calendario' para issue {issue['id']}: {calendar_value}")# Usa la nueva función para obtener el valor de "Calendario"
                if calendar_value == 'Calendario Google':
                    start_time = convert_millis_to_date(get_custom_field_value(issue, 'Hora de Inicio'))
                    end_time = convert_millis_to_date(get_custom_field_value(issue, 'Hora de Fin'))
                    location = get_custom_field_value(issue, 'Ubicacion')
                    attendees_emails = get_custom_field_value(issue, 'Invitados').split(',') if get_custom_field_value(issue, 'Invitados') else []
                    print(f"Procesando issue 'Calendario': {issue['id']} - {issue['summary']}")

                    event_google = {
                        "summary": issue['summary'],
                        "location": location,
                        "description": issue['description'],
                        "start": {
                            "dateTime": start_time,
                            "timeZone": "America/Mexico_City"
                        },
                        "end": {
                            "dateTime": end_time,
                            "timeZone": "America/Mexico_City"
                        },
                        "attendees": [{"email": email.strip()} for email in attendees_emails]
                    }

                    print(f"Procesando issue: {issue['id']} - {issue['summary']}")

                    google_event_id = find_event_by_summary(service_google, issue['summary'])


                     # Pausa entre sincronizaciones
                    
                
                    if google_event_id:
                       
                        print(f"Evento encontrado con ID: {google_event_id} - Actualizando...")
                        updated_event_google = service_google.events().update(calendarId='primary', eventId=google_event_id, body=event_google).execute()
                        print(f"Evento actualizado en Google Calendar: {updated_event_google.get('id')}")
                        # Llamada a la función para actualizar YouTrack basado en el evento de Google Calendar actualizado.
                        # print("Pausa antes de proceder con la sincronización inversa (si se implementa)...")
                        # update_youtrack_issue_from_google_event(service_google, issue['id'], google_event_id)
                    else:
                        print(f"Evento no encontrado para el summary: {issue['summary']} en Google Calendar - Creando uno nuevo...")
                        created_event_google = service_google.events().insert(calendarId='primary', body=event_google).execute()
                        google_event_id = created_event_google.get('id')
                        print(f"Evento creado en Google Calendar: {google_event_id}")
                        # Llamada a la función para actualizar YouTrack basado en el nuevo evento de Google Calendar.
                        # update_youtrack_issue_from_google_event(service_google, issue['id'], google_event_id)

                    # Crear evento en Outlook Calendar
                    # create_outlook_event(ms_token, issue)
                elif calendar_value == 'Calendario Outlook':
                    # Procesa la creación/actualización del evento en Outlook Calendar
                    user_id = 'usi.rommel.gomez@slp.gob.mx'  # Asegúrate de usar el user_id correcto para Outlook
                    create_outlook_event(ms_token, issue, user_id)
                else:
                    print(f"Ignorando issue no Calendario: {issue['id']} - {issue['summary']}")    

           


        except HttpError as error:
            print(f"Error ocurrió: {error}")

        # Espera un tiempo específico antes de volver a verificar, por ejemplo, 5 minutos.
        print("Esperando 2 minutos antes de la próxima verificación...")
        time.sleep(60)    


if __name__ == "__main__":
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES_GOOGLE)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES_GOOGLE)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service_google = build("calendar", "v3", credentials=creds)
    ms_token = get_microsoft_token()

    main_loop(service_google, ms_token)