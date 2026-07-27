import argparse
import time

import requests


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare uncached and cached chat latency."
        )
    )

    parser.add_argument(
        "--token",
        required=True,
        help="JWT bearer token.",
    )

    parser.add_argument(
        "--question",
        default=(
            "what is the difference between supervised and unsupervised learning?"
        ),
    )

    return parser.parse_args()


def send_request(
    token: str,
    question: str,
) -> tuple[float, dict]:
    started_at = time.perf_counter()

    response = requests.post(
        "http://127.0.0.1:8000/chat",
        headers={
            "Authorization": (
                f"Bearer {token}"
            )
        },
        json={
            "question": question,
            "candidate_k": 20,
            "final_k": 5,
        },
        timeout=300,
    )

    elapsed = time.perf_counter() - started_at

    response.raise_for_status()

    return elapsed, response.json()


def main() -> int:
    arguments = parse_arguments()

    first_seconds, first_result = send_request(
        token=arguments.token,
        question=arguments.question,
    )

    second_seconds, second_result = send_request(
        token=arguments.token,
        question=arguments.question,
    )

    print(
        f"First request: {first_seconds:.3f}s "
        f"(cache_hit={first_result['cache_hit']})"
    )

    print(
        f"Second request: {second_seconds:.3f}s "
        f"(cache_hit={second_result['cache_hit']})"
    )

    if second_seconds > 0:
        print(
            "Speedup: "
            f"{first_seconds / second_seconds:.2f}x"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())