import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List

from extractors.similarweb_parser import SimilarwebParser
from outputs.exporters import export_data

def setup_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

def load_settings(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Similarweb bulk data scraper"
    )
    parser.add_argument(
        "--config",
        default="src/config/settings.example.json",
        help="Path to settings JSON file",
    )
    parser.add_argument(
        "--input",
        dest="input_file",
        help="Optional override for input file path (CSV with 'domain' column or single column of domains)",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        help="Optional override for output file path",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["json", "csv", "xlsx"],
        help="Optional override for output format",
    )
    parser.add_argument(
        "--no-mock",
        dest="use_mock_data",
        action="store_false",
        help="Disable mock data and attempt real API calls",
    )
    parser.set_defaults(use_mock_data=None)  # so we can detect if user set it
    return parser.parse_args()

def load_domains_from_csv(path: str) -> List[str]:
    import csv

    if not os.path.exists(path):
        raise FileNotFoundError(f"Input file not found: {path}")

    domains: List[str] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        if "domain" in fieldnames:
            for row in reader:
                domain = (row.get("domain") or "").strip()
                if domain:
                    domains.append(domain)
        else:
            # Fallback: treat first column as domain
            f.seek(0)
            simple_reader = csv.reader(f)
            for row in simple_reader:
                if not row:
                    continue
                domain = row[0].strip()
                if domain and domain.lower() != "domain":
                    domains.append(domain)

    unique_domains = sorted(set(domains))
    return unique_domains

def build_parser_from_settings(settings: Dict[str, Any], cli_args: argparse.Namespace) -> SimilarwebParser:
    sw_conf = settings.get("similarweb", {})
    req_conf = settings.get("request", {})

    use_mock_data = sw_conf.get("use_mock_data", True)
    if cli_args.use_mock_data is not None:
        use_mock_data = cli_args.use_mock_data

    parser = SimilarwebParser(
        base_url=sw_conf.get("base_url", "https://api.similarweb.com/v1/website"),
        api_key_env=sw_conf.get("api_key_env", "SIMILARWEB_API_KEY"),
        timeout=req_conf.get("timeout", 10),
        max_retries=req_conf.get("max_retries", 3),
        backoff_factor=req_conf.get("backoff_factor", 0.5),
        use_mock_data=use_mock_data,
    )
    return parser

def main() -> int:
    args = parse_args()
    try:
        settings = load_settings(args.config)
    except Exception as e:
        print(f"Failed to load config: {e}", file=sys.stderr)
        return 1

    log_level = settings.get("log_level", "INFO")
    setup_logging(log_level)
    logger = logging.getLogger("main")

    input_file = args.input_file or settings.get("input_file", "data/inputs.sample.csv")
    output_path = args.output_path or settings.get("output_path", "data/sample_output.json")
    output_format = args.output_format or settings.get("output_format", "json")

    logger.info("Starting Similarweb scraper")
    logger.info("Input file: %s", input_file)
    logger.info("Output file: %s (%s)", output_path, output_format)

    try:
        domains = load_domains_from_csv(input_file)
    except Exception as e:
        logger.exception("Failed to load domains from CSV")
        return 1

    if not domains:
        logger.error("No domains found in input file: %s", input_file)
        return 1

    logger.info("Loaded %d unique domains", len(domains))

    parser = build_parser_from_settings(settings, args)
    results: List[Dict[str, Any]] = []
    for idx, domain in enumerate(domains, start=1):
        try:
            logger.info("Processing %d/%d: %s", idx, len(domains), domain)
            record = parser.get_domain_data(domain)
            results.append(record)
        except Exception as e:
            logger.exception("Failed to fetch data for domain '%s'", domain)

    if not results:
        logger.error("No data could be retrieved for any domain.")
        return 1

    try:
        export_data(results, output_format=output_format, output_path=output_path)
    except Exception as e:
        logger.exception("Failed to export data")
        return 1

    logger.info("Completed successfully. Exported %d records.", len(results))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())