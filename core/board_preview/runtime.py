from __future__ import annotations

from dataclasses import dataclass

from .request import PreviewRequest


@dataclass(slots=True)
class PreviewRuntimeState:
    active_key: str | None = None
    pending_request: PreviewRequest | None = None
    busy: bool = False

    def start_or_queue(self, request: PreviewRequest) -> bool:
        if self.busy:
            self.pending_request = request
            return False
        self.busy = True
        self.active_key = request.key
        self.pending_request = None
        return True

    def finish(self) -> PreviewRequest | None:
        pending = self.pending_request
        self.active_key = None
        self.pending_request = None
        self.busy = False
        return pending

    def cancel(self) -> None:
        self.active_key = None
        self.pending_request = None
        self.busy = False

    def is_current(self, request_key: object) -> bool:
        return self.busy and self.active_key == str(request_key or "")
