
import time
import sys

# ─────────────────────────────────────────────────────────────────────────────
# Utils: Colors & Logging
# ─────────────────────────────────────────────────────────────────────────────

class C:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    MAGENTA = '\033[35m'
    WHITE = '\033[97m'

# Telemetry: Track token usage across the session
class TokenTelemetry:
    def __init__(self, context_limit: int = 32768):
        self.total_input = 0
        self.total_output = 0
        self.steps = 0
        self.total_time = 0.0
        self.context_limit = context_limit

    def record(self, input_tokens: int, output_tokens: int, elapsed: float):
        self.total_input += input_tokens
        self.total_output += output_tokens
        self.total_time += elapsed
        self.steps += 1

    def step_summary(self, input_tokens: int, output_tokens: int, elapsed: float, has_img: bool) -> str:
        img_icon = "📸 " if has_img else ""
        total_session = self.total_input + self.total_output
        cnt_percent = (total_session / self.context_limit) * 100
        
        return (
            f"{C.DIM}[Step: +{input_tokens} in / +{output_tokens} out] "
            f"{C.CYAN}[Session Total: {total_session:,} ({cnt_percent:.1f}% of {self.context_limit//1024}k) | "
            f"{elapsed:.2f}s {img_icon}]{C.RESET}"
        )

    def session_summary(self) -> str:
        avg_time = self.total_time / self.steps if self.steps > 0 else 0
        return (
            f"{C.CYAN}📊 Session Telemetry:{C.RESET}\n"
            f"  • Total Input Tokens:  {C.BOLD}{self.total_input:,}{C.RESET}\n"
            f"  • Total Output Tokens: {C.BOLD}{self.total_output:,}{C.RESET}\n"
            f"  • Total Session Tokens: {C.BOLD}{self.total_input + self.total_output:,}{C.RESET}\n"
            f"  • Context Usage:       {C.BOLD}{((self.total_input + self.total_output)/self.context_limit)*100:.1f}%{C.RESET} (Limit: {self.context_limit})\n"
            f"  • Total Steps:         {self.steps}\n"
            f"  • Avg Time/Step:       {avg_time:.2f}s"
        )

