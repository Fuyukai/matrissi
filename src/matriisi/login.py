import sys

import trio

from matriisi import Identifier
from matriisi.http.httpclient import create_http_client


async def do_it(user_id: str, password: str):
    id = Identifier.parse(user_id)
    async with create_http_client(id.domain) as client:
        body = {
            "identifier": {"type": "m.id.user", "user": id.localpart},
            "device_id": "Matriisi",
            "initial_device_display_name": "Matriisi Library",
            "password": password,
            "type": "m.login.password",
            "refresh_token": True,
        }

        resp = await client.matrix_request("POST", "r0/login", body=body)
        print(f"User ID: {resp['user_id']}")
        print(f"Access token: {resp['access_token']}")


def main():
    args = sys.argv[1:]

    if len(args) != 2:
        print(f"Usage: {sys.argv[0]} @user:homeserver.tld password")
        sys.exit(1)

    userid, password = args

    trio.run(do_it, userid, password)


if __name__ == "__main__":
    main()
