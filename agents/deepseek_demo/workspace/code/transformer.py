import numpy as np

class LayerNorm:
    """Layer normalization with learnable scale and shift."""
    def __init__(self, d_model, eps=1e-5):
        self.eps = eps
        self.gamma = np.ones(d_model)
        self.beta = np.zeros(d_model)

    def forward(self, x):
        # x shape: (batch, seq, d_model)
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        self.x = x
        self.mean = mean
        self.var = var
        return self.gamma * (x - mean) / np.sqrt(var + self.eps) + self.beta

    def backward(self, dout):
        # Placeholder for training – not used in demo
        return dout

class MultiHeadAttention:
    """Scaled dot-product multi-head attention."""
    def __init__(self, d_model, num_heads):
        assert d_model % num_heads == 0
        self.d_model = d_model
        self.num_heads = num_heads
        self.head_dim = d_model // num_heads

        # Weight matrices
        self.W_q = np.random.randn(d_model, d_model) * 0.01
        self.W_k = np.random.randn(d_model, d_model) * 0.01
        self.W_v = np.random.randn(d_model, d_model) * 0.01
        self.W_o = np.random.randn(d_model, d_model) * 0.01

    def forward(self, query, key, value, mask=None):
        batch, seq_q, _ = query.shape
        seq_k = key.shape[1]

        # Linear projections
        Q = query @ self.W_q  # (batch, seq_q, d_model)
        K = key   @ self.W_k  # (batch, seq_k, d_model)
        V = value @ self.W_v  # (batch, seq_k, d_model)

        # Reshape to multi-head
        Q = Q.reshape(batch, seq_q, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)  # (b, h, sq, d)
        K = K.reshape(batch, seq_k, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)  # (b, h, sk, d)
        V = V.reshape(batch, seq_k, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)  # (b, h, sk, d)

        # Attention scores
        scale = np.sqrt(self.head_dim)
        scores = (Q @ K.transpose(0, 1, 3, 2)) / scale  # (b, h, sq, sk)

        if mask is not None:
            scores = np.where(mask, -1e9, scores)

        attn_weights = self._softmax(scores)  # (b, h, sq, sk)

        # Weighted sum
        context = attn_weights @ V  # (b, h, sq, d)

        # Concatenate heads
        context = context.transpose(0, 2, 1, 3).reshape(batch, seq_q, self.d_model)

        # Output projection
        out = context @ self.W_o
        self.cache = (Q, K, V, attn_weights)
        return out

    def _softmax(self, x):
        x_max = np.max(x, axis=-1, keepdims=True)
        e_x = np.exp(x - x_max)
        return e_x / np.sum(e_x, axis=-1, keepdims=True)

    def backward(self, dout):
        return dout  # Not implemented

class FeedForward:
    """Position-wise feed-forward network with ReLU activation."""
    def __init__(self, d_model, d_ff):
        self.W1 = np.random.randn(d_model, d_ff) * 0.01
        self.b1 = np.zeros(d_ff)
        self.W2 = np.random.randn(d_ff, d_model) * 0.01
        self.b2 = np.zeros(d_model)

    def forward(self, x):
        # x: (batch, seq, d_model)
        self.x = x
        hidden = np.maximum(0, x @ self.W1 + self.b1)  # ReLU
        self.hidden = hidden
        return hidden @ self.W2 + self.b2

class TransformerBlock:
    """One transformer encoder block: self-attention + feed-forward with pre-norm."""
    def __init__(self, d_model, num_heads, d_ff, dropout=0.0):
        self.ln1 = LayerNorm(d_model)
        self.self_attn = MultiHeadAttention(d_model, num_heads)
        self.ln2 = LayerNorm(d_model)
        self.ffn = FeedForward(d_model, d_ff)
        self.dropout = dropout

    def forward(self, x, mask=None):
        # Pre-norm residual
        attn_out = self.self_attn.forward(self.ln1.forward(x), self.ln1.forward(x), self.ln1.forward(x), mask)
        x = x + attn_out  # residual
        # Feed-forward
        ffn_out = self.ffn.forward(self.ln2.forward(x))
        x = x + ffn_out
        return x

class Transformer:
    """Simple transformer (encoder) model with embedding and positional encoding."""
    def __init__(self, vocab_size, d_model, num_heads, d_ff, num_layers, max_seq_len=512):
        self.vocab_size = vocab_size
        self.d_model = d_model
        self.token_embed = np.random.randn(vocab_size, d_model) * 0.01

        # Sinusoidal positional encodings
        pos_encoding = np.zeros((max_seq_len, d_model))
        positions = np.arange(max_seq_len)[:, np.newaxis]
        div_term = np.exp(np.arange(0, d_model, 2) * -(np.log(10000.0) / d_model))
        pos_encoding[:, 0::2] = np.sin(positions * div_term)
        pos_encoding[:, 1::2] = np.cos(positions * div_term)
        self.pos_encoding = pos_encoding

        self.blocks = [TransformerBlock(d_model, num_heads, d_ff) for _ in range(num_layers)]

    def forward(self, tokens):
        # tokens: (batch, seq_len)
        batch, seq = tokens.shape
        assert seq <= self.pos_encoding.shape[0], f"Sequence length {seq} exceeds max length {self.pos_encoding.shape[0]}"

        # Token embeddings + positional encoding
        x = self.token_embed[tokens] + self.pos_encoding[:seq]  # (batch, seq, d_model)

        for block in self.blocks:
            x = block.forward(x)

        return x  # (batch, seq, d_model)

def demo():
    """Run a small forward pass and assert shapes."""
    np.random.seed(42)
    vocab_size = 50
    d_model = 16
    num_heads = 4
    d_ff = 64
    num_layers = 2
    max_seq_len = 32
    batch = 2
    seq = 8

    model = Transformer(vocab_size, d_model, num_heads, d_ff, num_layers, max_seq_len)
    tokens = np.random.randint(0, vocab_size, size=(batch, seq))

    out = model.forward(tokens)
    print("Output shape:", out.shape)
    assert out.shape == (batch, seq, d_model), f"Expected {(batch, seq, d_model)}, got {out.shape}"
    print("Shapes OK")

    # Check that forward pass is deterministic
    out2 = model.forward(tokens)
    assert np.allclose(out, out2), "Determinism check failed"
    print("Determinism OK")

if __name__ == "__main__":
    demo()