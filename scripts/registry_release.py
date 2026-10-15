"""Anonymous Docker Hub lookup; fail closed on anything other than a missing manifest."""

import argparse
import json
import re
import urllib.error
import urllib.request

REPOSITORY = "mirage315/sut-reservation-management"


def resolve(tag, open_url=urllib.request.urlopen):
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
        raise ValueError("Invalid registry tag")
    with open_url(
        f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{REPOSITORY}:pull",
        timeout=30,
    ) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request(
        f"https://registry-1.docker.io/v2/{REPOSITORY}/manifests/{tag}",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json",
        },
        method="HEAD",
    )
    try:
        with open_url(request, timeout=30) as response:
            digest = response.headers["Docker-Content-Digest"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest or ""):
                raise ValueError("Registry did not return an immutable digest")
            return digest
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["require-absent", "resolve"])
    parser.add_argument("tag")
    args = parser.parse_args()
    digest = resolve(args.tag)
    if args.mode == "require-absent":
        if digest:
            raise SystemExit("Explicit release tag already exists; refusing to overwrite")
        print("Explicit tag is unused")
    elif digest:
        print(digest)
    else:
        raise SystemExit("Image tag does not exist")


if __name__ == "__main__":
    main()
