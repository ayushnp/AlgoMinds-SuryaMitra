import httpx
from typing import List, Optional
from core.config import settings

EXPO_PUSH_API_URL = "https://exp.host/--/api/v2/push/send"


async def send_expo_push_notification(
        token: str,  # The Expo Push Token for the user's device
        title: str,
        body: str,
        data: Optional[dict] = None
) -> None:
    """
    Sends a push notification to a single Expo token.
    """
    if not token:
        print("Notification skipped: No Expo token provided.")
        return

    message = {
        "to": token,
        "title": title,
        "body": body,
        "data": data if data is not None else {},
        "priority": "high",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                EXPO_PUSH_API_URL,
                json=[message],
                timeout=5.0
            )
            response.raise_for_status()  # Raise exception for bad status codes

            response_json = response.json()
            if response_json.get('errors'):
                print(f"Expo Push Error: {response_json['errors']}")
            else:
                print(f"Notification sent successfully to {token}")

        except httpx.HTTPStatusError as e:
            print(f"HTTP error sending Expo notification: {e}")
        except httpx.RequestError as e:
            print(f"Request error sending Expo notification: {e}")
        except Exception as e:
            print(f"Unknown error sending Expo notification: {e}")

# Note: In a real system, you'd fetch the user's Expo token from the 'users' collection
# when they log in or register their device.