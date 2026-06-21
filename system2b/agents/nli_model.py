"""
nli_model.py — Arabic NLI inference wrapper for the Verdict Engine.

Wraps ``joeddav/xlm-roberta-large-xnli`` (XLM-RoBERTa Large fine-tuned on
XNLI) as a singleton-style class.  The model is loaded exactly once at
construction time and reused for all subsequent inferences.

NLI framing convention (critical):
    PREMISE    = the retrieved proposition (what a trusted source asserts)
    HYPOTHESIS = the user's claim (what we are trying to verify)

This framing asks the model: "Given that this trusted proposition is true,
does it support, refute, or stay neutral toward the claim?"

Label mapping (model output → engine stance):
    0  contradiction  →  "REFUTES"
    1  neutral        →  "NEUTRAL"
    2  entailment     →  "SUPPORTS"
"""

from typing import Literal

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

Stance = Literal["SUPPORTS", "REFUTES", "NEUTRAL"]

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_MODEL_NAME = "joeddav/xlm-roberta-large-xnli"

# Index → Stance mapping (matches the model's label order)
_LABEL_MAP: dict[int, Stance] = {
    0: "REFUTES",   # contradiction
    1: "NEUTRAL",   # neutral
    2: "SUPPORTS",  # entailment
}


# ---------------------------------------------------------------------------
# NLI wrapper
# ---------------------------------------------------------------------------

class ArabicNLIModel:
    """
    Singleton-style wrapper around ``joeddav/xlm-roberta-large-xnli``.

    Load once, call many times.  The model is moved to GPU automatically
    when CUDA is available; otherwise it runs on CPU.

    Usage::

        nli = ArabicNLIModel()
        stance = nli.predict(claim="الأرض مسطحة", proposition="الأرض كروية الشكل")
        # → "REFUTES"
    """

    def __init__(self) -> None:
        print("[NLI] Loading model... (one-time, ~2.8GB)")

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[NLI] Using device: {self.device}")

        # transformers will auto-download on first run and use the local
        # cache (~/.cache/huggingface/) on subsequent runs.
        self.tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
        self.model = AutoModelForSequenceClassification.from_pretrained(_MODEL_NAME)

        self.model.to(self.device)
        self.model.eval()  # disable dropout — we are always in inference mode

        print("[NLI] Model ready.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, claim: str, proposition: str) -> Stance:
        """
        Run NLI for a single (proposition, claim) pair.

        Args:
            claim       : The Arabic claim under investigation (hypothesis).
            proposition : A trusted-source proposition to evaluate (premise).

        Returns:
            One of ``"SUPPORTS"``, ``"REFUTES"``, or ``"NEUTRAL"``.
        """
        return self._infer(claim, [proposition])[0]

    def predict_batch(self, claim: str, propositions: list[str]) -> list[Stance]:
        """
        Run NLI for a single claim against multiple propositions in one
        forward pass.

        Args:
            claim        : The Arabic claim under investigation (hypothesis).
            propositions : List of trusted-source propositions (premises).

        Returns:
            A list of stances in the same order as ``propositions``.
            Returns an empty list when ``propositions`` is empty.
        """
        if not propositions:
            return []

        return self._infer(claim, propositions)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _infer(self, claim: str, propositions: list[str]) -> list[Stance]:
        """
        Tokenize a batch of (proposition, claim) pairs and run one forward
        pass through the model.

        NLI convention: the tokenizer receives (premise, hypothesis), so
        proposition comes first, claim comes second.

        Args:
            claim        : Shared hypothesis for all pairs.
            propositions : List of premises.

        Returns:
            List of ``Stance`` values, one per proposition.
        """
        # Build parallel lists — tokenizer expects (premise, hypothesis) pairs.
        premises = propositions                    # trusted propositions
        hypotheses = [claim] * len(propositions)  # same claim repeated

        encodings = self.tokenizer(
            premises,
            hypotheses,
            padding=True,       # pad to the longest sequence in the batch
            truncation=True,    # truncate to the model's max token length
            return_tensors="pt",
        )

        # Move tensors to the same device as the model.
        encodings = {k: v.to(self.device) for k, v in encodings.items()}

        with torch.no_grad():
            logits = self.model(**encodings).logits  # (batch_size, 3)

        predicted_indices = logits.argmax(dim=-1).tolist()  # list[int]

        return [_LABEL_MAP[idx] for idx in predicted_indices]
