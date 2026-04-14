import argparse
import webbrowser
import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="wViewer — WiGLE WiFi map viewer")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    args = parser.parse_args()

    url = f"http://localhost:{args.port}"
    if not args.no_browser:
        webbrowser.open(url)

    uvicorn.run(
        "wviewer.app:app",
        host="127.0.0.1",
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
