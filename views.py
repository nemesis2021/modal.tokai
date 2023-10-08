import logging

from django.shortcuts import render, redirect
from django.http import HttpResponse
from .models import OIDCConfiguration, Credentials, APICredentials
from .logging import log_pactflow_response
import requests
import json

# Initializing logger
logger = logging.getLogger(__name__)

def social_media_login(request: HttpRequest, platform: str) -> HttpResponse:
    """
    This is a view to handle login credentials for the social media site.
    Retrieves the credentials or API keys stored in the database and sends them 
    to the requested platform for login.

    Args:
        request: HttpRequest object
        platform: str, name of the social media platform

    Returns:
        HttpResponse object
    """
    try:
        # Check if there are API keys stored for the platform
        api_keys = APICredentials.objects.filter(platform=platform)
        if not api_keys.exists():
            # If no API keys found, check for username and password
            login_details = Credentials.objects.filter(platform=platform)
            if not login_details.exists():
                return HttpResponse("No login credentials found for the requested platform.")
    except Exception as e:
        logger.error(f"Error while fetching credentials: {e}")
        return HttpResponse(f"Error while fetching credentials: {e}")


def oidc_auth(request: HttpRequest) -> HttpResponse:
    """ 
    This is a view to handle initial OIDC authentication request.  

    Args:
        request: HttpRequest object 

    Returns:
        HttpResponse object
    """
    try:
        if not (config := OIDCConfiguration.objects.first()):
            return HttpResponse("OIDC Configuration not found in database.")
        client_id = config.client_id
        redirect_uri = config.redirect_uris.split(',')[0].strip()

        auth_url = "https://api.bitbucket.org/2.0/workspaces/smodal/pipelines-config/identity/oidc"
            # Constructing and redirecting to authentication URL.
        return redirect(
            f"{auth_url}?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code"
        )
    except Exception as e:
        logger.error(f"Error during OIDC Auth: {e}")
        return HttpResponse(f"Error during OIDC Auth: {e}")


def oidc_callback(request: HttpRequest) -> HttpResponse:
    """
    This is a view to handle auth server's callback.

    Args:
        request: HttpRequest object

    Returns:
        HttpResponse object
    """
    try:
        if not (config := OIDCConfiguration.objects.first()):
            return HttpResponse("OIDC Configuration not found in database.")
        token_url = "https://api.bitbucket.org/2.0/workspaces/smodal/pipelines-config/identity/oidc/token"
        client_id = config.client_id
        redirect_uri = config.redirect_uris.split(',')[0].strip()
        client_secret = config.client_secret

        # Getting the authorization code from request parameters
        code = request.GET.get('code')

        # Constructing headers and body for token request.
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        body = {'grant_type': 'authorization_code', 'code': code, 'client_id': client_id, 'client_secret': client_secret, 'redirect_uri': redirect_uri }

        # Making POST request to get tokens.
        r = requests.post(token_url, headers=headers, data=body)

        if r.status_code == 200:
            # If request is successful, redirect to home page after storing tokens.
            access_token = r.json().get('access_token')

                # Making a request to Pactflow.
            pactflow_headers = {'Authorization': f'Bearer {access_token}'}
            r_pactflow = requests.get('https://modaltokai-smodal.pactflow.io', headers=pactflow_headers)
            if r_pactflow.status_code == 200:
                # Save pactflow response details
                response_headers = json.dumps(dict(r_pactflow.headers))
                response_body = json.dumps(r_pactflow.json())

                config.pactflow_response_headers = response_headers
                config.pactflow_response_body = response_body
                config.save()

                # Log pactflow response
                log_pactflow_response(response_headers, response_body)
            else:
                return HttpResponse("Error while fetching data from Pactflow. Please try again")

            # After storing the tokens, redirect as per your application's flow.
            return redirect('/home/')
        else:
            return HttpResponse("Error while fetching tokens. Please try again.")
    except Exception as e:
        logger.error(f"Error during OIDC Callback: {e}")
        return HttpResponse(f"Error during OIDC Callback: {e}")