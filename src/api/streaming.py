"""
Real-time Streaming API using SSE (Server-Sent Events).

Features:
- Server-Sent Events for real-time updates
- WebSocket fallback support
- Progress tracking for long-running operations
- Client SDK examples
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Stream event types."""
    PROGRESS = "progress"
    STATUS = "status"
    RESULT = "result"
    ERROR = "error"
    COMPLETE = "complete"
    HEARTBEAT = "heartbeat"


@dataclass
class StreamEvent:
    """Stream event structure."""
    event_type: EventType
    data: Dict[str, Any]
    timestamp: str = None
    event_id: str = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_sse_format(self) -> str:
        """Format as SSE message."""
        lines = []

        if self.event_id:
            lines.append(f"id: {self.event_id}")

        lines.append(f"event: {self.event_type.value}")
        lines.append(f"data: {json.dumps(self.data)}")
        lines.append("")  # Empty line to end event

        return "\n".join(lines)


class StreamManager:
    """
    Manages real-time streaming connections.

    Features:
    - SSE event streaming
    - Client connection tracking
    - Automatic heartbeat
    - Backpressure handling
    """

    def __init__(self, heartbeat_interval: int = 30):
        """
        Initialize stream manager.

        Args:
            heartbeat_interval: Seconds between heartbeats
        """
        self.heartbeat_interval = heartbeat_interval
        self._active_streams: Dict[str, asyncio.Queue] = {}
        self._stream_metadata: Dict[str, Dict] = {}
        self._event_counter = 0

    def create_stream(self, stream_id: str, metadata: Optional[Dict] = None):
        """
        Create new stream.

        Args:
            stream_id: Unique stream identifier
            metadata: Optional stream metadata
        """
        if stream_id in self._active_streams:
            logger.warning(f"Stream {stream_id} already exists")
            return

        self._active_streams[stream_id] = asyncio.Queue(maxsize=100)
        self._stream_metadata[stream_id] = {
            "created_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            "events_sent": 0
        }

        logger.info(f"Created stream {stream_id}")

    async def send_event(
        self,
        stream_id: str,
        event_type: EventType,
        data: Dict[str, Any]
    ):
        """
        Send event to stream.

        Args:
            stream_id: Target stream
            event_type: Event type
            data: Event data
        """
        if stream_id not in self._active_streams:
            logger.error(f"Stream {stream_id} not found")
            return

        self._event_counter += 1
        event = StreamEvent(
            event_type=event_type,
            data=data,
            event_id=str(self._event_counter)
        )

        try:
            await asyncio.wait_for(
                self._active_streams[stream_id].put(event),
                timeout=5.0
            )
            self._stream_metadata[stream_id]["events_sent"] += 1

        except asyncio.TimeoutError:
            logger.warning(f"Stream {stream_id} queue full, dropping event")

    async def stream_generator(
        self,
        stream_id: str
    ) -> AsyncGenerator[str, None]:
        """
        Generate SSE stream for client.

        Args:
            stream_id: Stream to consume

        Yields:
            SSE formatted events
        """
        if stream_id not in self._active_streams:
            yield f"event: error\ndata: {{\"error\": \"Stream not found\"}}\n\n"
            return

        queue = self._active_streams[stream_id]
        last_heartbeat = time.time()

        try:
            while True:
                # Send heartbeat if needed
                if time.time() - last_heartbeat > self.heartbeat_interval:
                    heartbeat = StreamEvent(
                        event_type=EventType.HEARTBEAT,
                        data={"timestamp": datetime.utcnow().isoformat()}
                    )
                    yield heartbeat.to_sse_format()
                    last_heartbeat = time.time()

                # Get next event (with timeout)
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=1.0
                    )

                    yield event.to_sse_format()

                    # Check for completion
                    if event.event_type == EventType.COMPLETE:
                        break

                except asyncio.TimeoutError:
                    continue

        except asyncio.CancelledError:
            logger.info(f"Stream {stream_id} cancelled")

        finally:
            self.close_stream(stream_id)

    def close_stream(self, stream_id: str):
        """Close and cleanup stream."""
        if stream_id in self._active_streams:
            del self._active_streams[stream_id]
            del self._stream_metadata[stream_id]
            logger.info(f"Closed stream {stream_id}")

    def get_active_streams(self) -> List[str]:
        """Get list of active stream IDs."""
        return list(self._active_streams.keys())

    def get_stream_metadata(self, stream_id: str) -> Optional[Dict]:
        """Get stream metadata."""
        return self._stream_metadata.get(stream_id)


class ProgressTracker:
    """
    Track progress for long-running operations.

    Features:
    - Stage-based progress
    - Estimated time remaining
    - Error handling
    """

    def __init__(self, stream_manager: StreamManager, stream_id: str):
        """
        Initialize progress tracker.

        Args:
            stream_manager: Stream manager instance
            stream_id: Target stream ID
        """
        self.stream_manager = stream_manager
        self.stream_id = stream_id
        self.stages: List[str] = []
        self.current_stage: int = 0
        self.start_time = time.time()

    async def start(self, stages: List[str]):
        """
        Start progress tracking.

        Args:
            stages: List of stage names
        """
        self.stages = stages
        self.current_stage = 0
        self.start_time = time.time()

        await self.stream_manager.send_event(
            self.stream_id,
            EventType.STATUS,
            {
                "status": "started",
                "total_stages": len(stages),
                "stages": stages
            }
        )

    async def update_stage(
        self,
        stage_index: int,
        progress: float,
        message: Optional[str] = None
    ):
        """
        Update stage progress.

        Args:
            stage_index: Current stage index
            progress: Progress within stage (0.0 - 1.0)
            message: Optional status message
        """
        self.current_stage = stage_index

        elapsed = time.time() - self.start_time
        overall_progress = (stage_index + progress) / len(self.stages)

        # Estimate time remaining
        eta = None
        if overall_progress > 0:
            total_time = elapsed / overall_progress
            eta = total_time - elapsed

        await self.stream_manager.send_event(
            self.stream_id,
            EventType.PROGRESS,
            {
                "stage": self.stages[stage_index],
                "stage_index": stage_index,
                "stage_progress": progress,
                "overall_progress": overall_progress,
                "elapsed_seconds": elapsed,
                "eta_seconds": eta,
                "message": message
            }
        )

    async def complete(self, result: Dict[str, Any]):
        """
        Mark operation as complete.

        Args:
            result: Final result data
        """
        elapsed = time.time() - self.start_time

        await self.stream_manager.send_event(
            self.stream_id,
            EventType.RESULT,
            {
                "result": result,
                "elapsed_seconds": elapsed
            }
        )

        await self.stream_manager.send_event(
            self.stream_id,
            EventType.COMPLETE,
            {"status": "success"}
        )

    async def error(self, error_message: str, error_details: Optional[Dict] = None):
        """
        Report error.

        Args:
            error_message: Error description
            error_details: Additional error context
        """
        await self.stream_manager.send_event(
            self.stream_id,
            EventType.ERROR,
            {
                "error": error_message,
                "details": error_details or {}
            }
        )

        await self.stream_manager.send_event(
            self.stream_id,
            EventType.COMPLETE,
            {"status": "error"}
        )


# Client SDK Example (Python)
CLIENT_SDK_PYTHON = '''
"""
sanjai-insight Streaming Client SDK (Python)

Usage:
    client = StreamingClient("https://api.sanjai.com")
    async for event in client.stream("job_123"):
        if event["type"] == "progress":
            print(f"Progress: {event['data']['overall_progress']:.0%}")
        elif event["type"] == "result":
            print(f"Result: {event['data']['result']}")
"""

import asyncio
import json
from typing import AsyncGenerator, Dict
import aiohttp


class StreamingClient:
    """Streaming API client."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def stream(self, stream_id: str) -> AsyncGenerator[Dict, None]:
        """
        Stream events from server.

        Args:
            stream_id: Stream identifier

        Yields:
            Event dictionaries
        """
        url = f"{self.base_url}/api/stream/{stream_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Stream error: {response.status}")

                async for line in response.content:
                    line = line.decode("utf-8").strip()

                    if not line:
                        continue

                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data = json.loads(line[5:].strip())
                        yield {
                            "type": event_type,
                            "data": data
                        }

                        if event_type == "complete":
                            break


# Example usage
async def example():
    client = StreamingClient(
        base_url="https://api.sanjai.com",
        api_key="sk_tenant_xyz_..."
    )

    async for event in client.stream("job_123"):
        if event["type"] == "progress":
            progress = event["data"]["overall_progress"]
            print(f"Progress: {progress:.0%}")
        elif event["type"] == "result":
            print(f"Result: {event['data']['result']}")
        elif event["type"] == "error":
            print(f"Error: {event['data']['error']}")


if __name__ == "__main__":
    asyncio.run(example())
'''

# Client SDK Example (JavaScript)
CLIENT_SDK_JS = '''
/**
 * sanjai-insight Streaming Client SDK (JavaScript/TypeScript)
 *
 * Usage:
 *   const client = new StreamingClient("https://api.sanjai.com", "sk_...");
 *   for await (const event of client.stream("job_123")) {
 *     if (event.type === "progress") {
 *       console.log(`Progress: ${(event.data.overall_progress * 100).toFixed(0)}%`);
 *     }
 *   }
 */

class StreamingClient {
  constructor(baseUrl, apiKey) {
    this.baseUrl = baseUrl.replace(/\\/$/, "");
    this.apiKey = apiKey;
  }

  async* stream(streamId) {
    const url = `${this.baseUrl}/api/stream/${streamId}`;
    const response = await fetch(url, {
      headers: {
        "Authorization": `Bearer ${this.apiKey}`,
        "Accept": "text/event-stream"
      }
    });

    if (!response.ok) {
      throw new Error(`Stream error: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = "";
    let eventType = null;

    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.trim()) continue;

        if (line.startsWith("event:")) {
          eventType = line.substring(6).trim();
        } else if (line.startsWith("data:")) {
          const data = JSON.parse(line.substring(5).trim());
          yield { type: eventType, data };

          if (eventType === "complete") {
            return;
          }
        }
      }
    }
  }
}

// Example usage
async function example() {
  const client = new StreamingClient(
    "https://api.sanjai.com",
    "sk_tenant_xyz_..."
  );

  for await (const event of client.stream("job_123")) {
    if (event.type === "progress") {
      console.log(`Progress: ${(event.data.overall_progress * 100).toFixed(0)}%`);
    } else if (event.type === "result") {
      console.log("Result:", event.data.result);
    } else if (event.type === "error") {
      console.error("Error:", event.data.error);
    }
  }
}

export { StreamingClient };
'''


# Flask integration example
def register_streaming_routes(app, stream_manager: StreamManager):
    """
    Register streaming routes with Flask app.

    Args:
        app: Flask application
        stream_manager: StreamManager instance
    """
    from flask import Response, request, jsonify

    @app.route("/api/stream/<stream_id>", methods=["GET"])
    async def stream_endpoint(stream_id: str):
        """SSE streaming endpoint."""

        async def generate():
            async for event in stream_manager.stream_generator(stream_id):
                yield event

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
        )

    @app.route("/api/stream/<stream_id>/status", methods=["GET"])
    def stream_status(stream_id: str):
        """Get stream metadata."""
        metadata = stream_manager.get_stream_metadata(stream_id)
        if not metadata:
            return jsonify({"error": "Stream not found"}), 404

        return jsonify(metadata)

    @app.route("/api/streams/active", methods=["GET"])
    def active_streams():
        """List active streams."""
        streams = stream_manager.get_active_streams()
        return jsonify({"streams": streams, "count": len(streams)})
