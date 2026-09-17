"""Local MLX server with an explicit, recorded Mistral tokenizer correction.

Uses the installed MLX server CLI unchanged. This wrapper is only for subsequent
diagnostics, never a silent replacement for the legacy symmetry-audit runtime.
"""

from mlx_lm import server


class CorrectedMistralProvider(server.ModelProvider):
    def __init__(self, args):
        if not args.model or "mistral" not in args.model.lower():
            raise ValueError("this wrapper is restricted to the Mistral model")
        super().__init__(args)
        self._tokenizer_config["fix_mistral_regex"] = True


if __name__ == "__main__":
    server.ModelProvider = CorrectedMistralProvider
    server.main()
