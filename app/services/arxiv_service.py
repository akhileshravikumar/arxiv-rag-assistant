import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

import requests


ARXIV_API_URL = "https://export.arxiv.org/api/query"

NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
}

HEADERS = {
    "User-Agent": (
        "ArxivRAGAssistant/0.1 "
        "(contact: akhileshravikumar2@gmail.com)"
    )
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    return " ".join(value.split())


def normalize_arxiv_id(value: str) -> str:
    normalized = value.strip()

    prefixes = (
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
        "https://arxiv.org/pdf/",
        "http://arxiv.org/pdf/",
    )

    for prefix in prefixes:
        normalized = normalized.removeprefix(prefix)

    normalized = normalized.removesuffix(".pdf")

    if not normalized:
        raise ValueError("A valid arXiv ID is required.")

    return normalized


def parse_arxiv_published_date(
    published_value: str,
) -> date:
    if not published_value:
        raise ValueError("Published date is missing.")

    published_datetime = datetime.fromisoformat(
        published_value.replace("Z", "+00:00")
    )

    return published_datetime.date()


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(
        r'[<>:"/\\|?*]',
        "",
        value,
    )
    cleaned = re.sub(
        r"\s+",
        "_",
        cleaned.strip(),
    )

    return cleaned[:120] or "untitled_paper"


def extract_arxiv_id(entry_id: str) -> str:
    return entry_id.rstrip("/").split("/")[-1]


def build_search_query_url(
    search_term: str,
    max_results: int,
) -> str:
    if not search_term.strip():
        raise ValueError("Search term cannot be empty.")

    if max_results < 1 or max_results > 100:
        raise ValueError(
            "max_results must be between 1 and 100."
        )

    parameters = {
        "search_query": f'all:"{search_term.strip()}"',
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    return f"{ARXIV_API_URL}?{urlencode(parameters)}"


def build_id_query_url(arxiv_id: str) -> str:
    normalized_id = normalize_arxiv_id(arxiv_id)

    parameters = {
        "id_list": normalized_id,
        "start": 0,
        "max_results": 1,
    }

    return f"{ARXIV_API_URL}?{urlencode(parameters)}"


def find_pdf_url(
    entry: ET.Element,
) -> str | None:
    for link in entry.findall(
        "atom:link",
        NAMESPACES,
    ):
        link_title = link.attrib.get("title")
        link_type = link.attrib.get("type")
        href = link.attrib.get("href")

        if link_title == "pdf" and href:
            return href

        if (
            link_type == "application/pdf"
            and href
        ):
            return href

    return None


def parse_entries(
    xml_content: bytes,
) -> list[dict]:
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise RuntimeError(
            "The arXiv API returned invalid XML."
        ) from exc

    papers: list[dict] = []

    for entry in root.findall(
        "atom:entry",
        NAMESPACES,
    ):
        entry_id = normalize_text(
            entry.findtext(
                "atom:id",
                namespaces=NAMESPACES,
            )
        )

        title = normalize_text(
            entry.findtext(
                "atom:title",
                namespaces=NAMESPACES,
            )
        )

        summary = normalize_text(
            entry.findtext(
                "atom:summary",
                namespaces=NAMESPACES,
            )
        )

        published = normalize_text(
            entry.findtext(
                "atom:published",
                namespaces=NAMESPACES,
            )
        )

        updated = normalize_text(
            entry.findtext(
                "atom:updated",
                namespaces=NAMESPACES,
            )
        )

        authors: list[str] = []

        for author_element in entry.findall(
            "atom:author",
            NAMESPACES,
        ):
            author_name = normalize_text(
                author_element.findtext(
                    "atom:name",
                    namespaces=NAMESPACES,
                )
            )

            if author_name:
                authors.append(author_name)

        pdf_url = find_pdf_url(entry)

        papers.append(
            {
                "arxiv_id": extract_arxiv_id(
                    entry_id
                ),
                "title": title,
                "authors": authors,
                "published": published,
                "updated": updated,
                "summary": summary,
                "abstract_url": entry_id,
                "pdf_url": pdf_url,
            }
        )

    return papers


def request_arxiv(
    query_url: str,
    timeout_seconds: int = 30,
) -> list[dict]:
    try:
        response = requests.get(
            query_url,
            headers=HEADERS,
            timeout=timeout_seconds,
        )
        response.raise_for_status()

    except requests.Timeout as exc:
        raise RuntimeError(
            "The arXiv API request timed out."
        ) from exc

    except requests.RequestException as exc:
        raise RuntimeError(
            f"The arXiv API request failed: {exc}"
        ) from exc

    return parse_entries(response.content)


def search_arxiv(
    search_term: str,
    max_results: int = 5,
) -> list[dict]:
    query_url = build_search_query_url(
        search_term=search_term,
        max_results=max_results,
    )

    return request_arxiv(query_url)


def fetch_arxiv_paper(
    arxiv_id: str,
) -> dict:
    normalized_id = normalize_arxiv_id(arxiv_id)

    papers = request_arxiv(
        build_id_query_url(normalized_id)
    )

    if not papers:
        raise RuntimeError(
            f"No arXiv paper was found for ID "
            f"{normalized_id}."
        )

    paper = papers[0]

    returned_base_id = (
        paper["arxiv_id"]
        .split("v", maxsplit=1)[0]
    )
    requested_base_id = (
        normalized_id
        .split("v", maxsplit=1)[0]
    )

    if returned_base_id != requested_base_id:
        raise RuntimeError(
            f"No exact arXiv match was found for "
            f"{normalized_id}."
        )

    return paper


def build_pdf_destination(
    paper: dict,
    raw_data_directory: Path,
) -> Path:
    filename = (
        f"{paper['arxiv_id'].replace('/', '_')}_"
        f"{sanitize_filename(paper['title'])}.pdf"
    )

    return raw_data_directory / filename


def download_pdf(
    pdf_url: str,
    destination: Path,
    timeout_seconds: int = 120,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_destination = (
        destination.with_suffix(".pdf.part")
    )

    try:
        with requests.get(
            pdf_url,
            headers=HEADERS,
            timeout=timeout_seconds,
            stream=True,
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type",
                "",
            ).lower()

            if "pdf" not in content_type:
                raise RuntimeError(
                    "Expected PDF content but received "
                    f"Content-Type: {content_type}"
                )

            with temporary_destination.open(
                "wb"
            ) as pdf_file:
                for chunk in response.iter_content(
                    chunk_size=8192
                ):
                    if chunk:
                        pdf_file.write(chunk)

        if (
            not temporary_destination.exists()
            or temporary_destination.stat().st_size == 0
        ):
            raise RuntimeError(
                "The downloaded PDF is empty."
            )

        temporary_destination.replace(
            destination
        )

    except requests.RequestException as exc:
        temporary_destination.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            f"PDF download failed: {exc}"
        ) from exc

    except OSError as exc:
        temporary_destination.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            f"Could not save PDF: {exc}"
        ) from exc


def download_arxiv_paper(
    paper: dict,
    raw_data_directory: Path,
) -> dict:
    processed_paper = dict(paper)

    pdf_url = processed_paper.get("pdf_url")

    if not pdf_url:
        processed_paper[
            "download_status"
        ] = "missing_pdf_url"

        return processed_paper

    destination = build_pdf_destination(
        paper=processed_paper,
        raw_data_directory=raw_data_directory,
    )

    if (
        destination.exists()
        and destination.stat().st_size > 0
    ):
        processed_paper[
            "download_status"
        ] = "already_exists"
    else:
        download_pdf(
            pdf_url=pdf_url,
            destination=destination,
        )

        processed_paper[
            "download_status"
        ] = "downloaded"

    processed_paper[
        "local_pdf_path"
    ] = str(destination)

    return processed_paper


def process_papers(
    papers: list[dict],
    raw_data_directory: Path,
    delay_seconds: int = 3,
) -> list[dict]:
    processed_papers: list[dict] = []

    for index, paper in enumerate(
        papers,
        start=1,
    ):
        try:
            processed_paper = (
                download_arxiv_paper(
                    paper=paper,
                    raw_data_directory=(
                        raw_data_directory
                    ),
                )
            )

        except RuntimeError as exc:
            processed_paper = dict(paper)
            processed_paper[
                "download_status"
            ] = "failed"
            processed_paper[
                "download_error"
            ] = str(exc)

        processed_papers.append(
            processed_paper
        )

        if (
            index < len(papers)
            and delay_seconds > 0
        ):
            time.sleep(delay_seconds)

    return processed_papers


def load_existing_metadata(
    metadata_file: Path,
) -> list[dict]:
    if not metadata_file.exists():
        return []

    try:
        with metadata_file.open(
            "r",
            encoding="utf-8",
        ) as file:
            content = json.load(file)

    except (
        json.JSONDecodeError,
        OSError,
    ) as exc:
        raise RuntimeError(
            f"Could not read metadata file: "
            f"{metadata_file}"
        ) from exc

    return content if isinstance(content, list) else []


def save_metadata(
    new_papers: list[dict],
    metadata_file: Path,
) -> None:
    metadata_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing_papers = load_existing_metadata(
        metadata_file
    )

    papers_by_id = {
        paper["arxiv_id"]: paper
        for paper in existing_papers
        if paper.get("arxiv_id")
    }

    for paper in new_papers:
        arxiv_id = paper.get("arxiv_id")

        if arxiv_id:
            papers_by_id[arxiv_id] = paper

    try:
        with metadata_file.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                list(papers_by_id.values()),
                file,
                indent=2,
                ensure_ascii=False,
            )

    except OSError as exc:
        raise RuntimeError(
            f"Could not save metadata file: "
            f"{metadata_file}"
        ) from exc