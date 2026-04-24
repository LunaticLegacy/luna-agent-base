```python
import numpy as np
from typing import List, Tuple, Optional

# ==============================
# Helper functions
# ==============================
def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """Numerically stable softmax."""
    x_max = np.max(x, axis=axis, keepdims=True)
    exp_x = np.exp(x - x_max)
    return exp_x / np.sum(exp_x, axis=axis, keepdims=True)

def layer_norm(x: np.ndarray, gamma: np.ndarray, beta: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    """Layer normalization. x shape: (..., D). gamma, beta: (D,). Returns normalized output."""
    mean = np.mean(x, axis=-1, keepdims=True)
    var = np.var(x, axis=-1, keepdims=True)
    x_hat = (x - mean) / np.sqrt(var + eps)
    return gamma * x_hat + beta

def layer_norm_backward(dout: np.ndarray, x: np.ndarray, gamma: np.ndarray,
                        cache: dict) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Backward for layer norm. dout shape same as x. Returns (dx, dgamma, dbeta)."""
    mean = cache['mean']
    var = cache['var']
    eps = cache['eps']
    N, D = x.shape  # assume 2D for simplicity, but works for any shape
    x_hat = cache['x_hat']
    # gradient w.r.t. x_hat
    dx_hat = dout * gamma
    # gradient w.r.t. variance
    dvar = np.sum(dx_hat * (x - mean) * -0.5 * (var + eps) ** (-1.5), axis=-1, keepdims=True)
    # gradient w.r.t. mean
    dmean = np.sum(dx_hat * -1.0 / np.sqrt(var + eps), axis=-1, keepdims=True) + dvar * np.mean(-2.0 * (x - mean), axis=-1, keepdims=True)
    # gradient w.r.t. x
    dx = dx_hat / np.sqrt(var + eps) + dvar * 2.0 * (x - mean) / N + dmean / N
    # gradients for gamma and beta
    dgamma = np.sum(dout * x_hat, axis=0)
    dbeta = np.sum(dout, axis=0)
    return dx, dgamma, dbeta

def xavier_init(shape: Tuple[int, ...]) -> np.ndarray:
    """Xavier uniform initialization."""
    fan_in, fan_out = shape[-2], shape[-1]
    limit = np.sqrt(6.0 / (fan_in + fan_out))
    return np.random.uniform(-limit, limit, size=shape)

# ==============================
# Transformer Components
# ==============================
class MultiHeadAttention:
    """Multi-head self-attention with manual forward/backward."""
    def __init__(self, d_model: int, n_heads: int):
        assert d_model % n_heads == 0, "d_model must be divisible by n_heads"
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_k = d_model // n_heads

        # Parameters
        self.W_q = xavier_init((d_model, d_model))
        self.W_k = xavier_init((d_model, d_model))
        self.W_v = xavier_init((d_model, d_model))
        self.W_o = xavier_init((d_model, d_model))

        # Gradients
        self.dW_q = np.zeros_like(self.W_q)
        self.dW_k = np.zeros_like(self.W_k)
        self.dW_v = np.zeros_like(self.W_v)
        self.dW_o = np.zeros_like(self.W_o)

        # Cache
        self.cache = {}

    def forward(self, Q: np.ndarray, K: np.ndarray, V: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Q, K, V shape: (batch, seq_len, d_model)
        mask shape: (batch, seq_len, seq_len) or broadcastable
        Returns output shape: (batch, seq_len, d_model)
        """
        batch, seq_len, _ = Q.shape
        # Linear projections
        Q_proj = Q @ self.W_q  # (b, seq, d_model)
        K_proj = K @ self.W_k
        V_proj = V @ self.W_v

        # Reshape to multi-head: (b, n_heads, seq, d_k)
        Q_heads = Q_proj.reshape(batch, seq_len, self.n_heads, self.d_k).transpose(0, 2, 1, 3)
        K_heads = K_proj.reshape(batch, seq_len, self.n_heads, self.d_k).transpose(0, 2, 1, 3)
        V_heads = V_proj.reshape(batch, seq_len, self.n_heads, self.d_k).transpose(0, 2, 1, 3)

        # Scaled dot-product attention
        scores = Q_heads @ K_heads.transpose(0, 1, 3, 2) / np.sqrt(self.d_k)  # (b, n_heads, seq, seq)

        if mask is not None:
            # mask additive: large negative for masked positions
            scores = scores + mask

        attn_weights = softmax(scores, axis=-1)  # (b, n_heads, seq, seq)
        attn_output = attn_weights @ V_heads  # (b, n_heads, seq, d_k)

        # Concatenate heads
        attn_output = attn_output.transpose(0, 2, 1, 3).reshape(batch, seq_len, self.d_model)  # (b, seq, d_model)

        # Final projection
        output = attn_output @ self.W_o  # (b, seq, d_model)

        # Cache for backward
        self.cache = {
            'Q': Q, 'K': K, 'V': V,
            'Q_proj': Q_proj, 'K_proj': K_proj, 'V_proj': V_proj,
            'Q_heads': Q_heads, 'K_heads': K_heads, 'V_heads': V_heads,
            'scores': scores, 'attn_weights': attn_weights,
            'attn_output': attn_output,
            'mask': mask,
            'batch': batch, 'seq_len': seq_len
        }
        return output

    def backward(self, dout: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Gradient of loss w.r.t. Q, K, V inputs.
        dout shape: (batch, seq_len, d_model)
        Returns dQ, dK, dV each shape (batch, seq_len, d_model)
        """
        cache = self.cache
        batch, seq_len, _ = dout.shape
        Q = cache['Q']; K = cache['K']; V = cache['V']
        Q_proj = cache['Q_proj']; K_proj = cache['K_proj']; V_proj = cache['V_proj']
        Q_heads = cache['Q_heads']; K_heads = cache['K_heads']; V_heads = cache['V_heads']
        scores = cache['scores']; attn_weights = cache['attn_weights']
        attn_output = cache['attn_output']
        mask = cache['mask']

        # Gradient w.r.t. W_o
        dW_o = attn_output.reshape(batch * seq_len, self.d_model).T @ dout.reshape(batch * seq_len, self.d_model)
        self.dW_o = dW_o

        # Backprop through output projection
        dattn = dout @ self.W_o.T  # (b, seq, d_model)
        # Reshape to heads
        dattn_heads = dattn.reshape(batch, seq_len, self.n_heads, self.d_k).transpose(0, 2, 1, 3)  # (b, n_heads, seq, d_k)

        # Backprop through attention: dV_heads, dattn_weights, dQ_heads, dK_heads
        # dout_for_V = attn_weights^T @ dattn_heads (since V contributes through attn_output = weights * V)
        # Actually: attn_output = weights @ V, so dV = weights^T @ dattn (in batch matmul)
        # Careful with shapes: (b, n_heads, seq, d_k) = (b, n_heads, seq, seq) @ (b, n_heads, seq, d_k)
        # So dV_heads = weights^T @ dattn_heads
        dV_heads = attn_weights.transpose(0, 1, 3, 2) @ dattn_heads  # (b, n_heads, seq, d_k)

        # dweights = dattn_heads @ V_heads^T
        # But also softmax backward: dscores = dweights * (softmax - softmax * softmax^T) but we can use formula:
        # For softmax with cross-entropy use dedicated loss, but here attention output uses differentiable softmax.
        # General formula: for y = softmax(x), dy = y * (dx - sum(dx * y, axis=-1, keepdims=True))
        dscores = np.zeros_like(scores)
        # dattn_weights = dattn_heads @ V_heads.transpose(0,1,3,2) (b, n_heads, seq, seq)
        dattn_weights = dattn_heads @ V_heads.transpose(0, 1, 3, 2)  # (b, n_heads, seq, seq)
        # Softmax backward
        dscores = attn_weights * (dattn_weights - np.sum(dattn_weights * attn_weights, axis=-1, keepdims=True))
        # If mask applied, we need to ignore masked positions for softmax but gradients flow through unmasked only.
        # Since softmax is applied after adding mask, we treat mask as additive contribution to scores.
        # So mask effect is absorbed in scores; we continue.

        # Backprop through scale
        dscores /= np.sqrt(self.d_k)

        # dQ_heads = dscores @ K_heads
        dQ_heads = dscores @ K_heads  # (b,n_heads,seq,d_k)
        # dK_heads = dscores.transpose(0,1,3,2) @ Q_heads  # careful: symmetric
        dK_heads = dscores.transpose(0, 1, 3, 2) @ Q_heads

        # Reshape dQ_heads, dK_heads, dV_heads back to (b, seq, d_model)
        dQ_proj = dQ_heads.transpose(0, 2, 1, 3).reshape(batch, seq_len, self.d_model)
        dK_proj = dK_heads.transpose(0, 2, 1, 3).reshape(batch, seq_len, self.d_model)
        dV_proj = dV_heads.transpose(0, 2, 1, 3).reshape(batch, seq_len, self.d_model)

        # Backprop through linear projections: dQ = dQ_proj @ W_q^T   (since Q_proj = Q @ W_q)
        # Actually gradient w.r.t. Q: dQ = dQ_proj @ W_q.T
        dQ = dQ_proj @ self.W_q.T
        dK = dK_proj @ self.W_k.T
        dV = dV_proj @ self.W_v.T

        # Gradients for weight matrices
        # dW_q = Q^T @ dQ_proj (averaged over batch? No, sum across batch)
        self.dW_q = Q.reshape(batch * seq_len, self.d_model).T @ dQ_proj.reshape(batch * seq_len, self.d_model)
        self.dW_k = K.reshape(batch * seq_len, self.d_model).T @ dK_proj.reshape(batch * seq_len, self.d_model)
        self.dW_v = V.reshape(batch * seq_len, self.d_model).T @ dV_proj.reshape(batch * seq_len, self.d_model)

        return dQ, dK, dV

class FeedForward:
    """Two-layer feed-forward with ReLU."""
    def __init__(self, d_model: int, d_ff: int):
        self.W1 = xavier_init((d_model, d_ff))
        self.b1 = np.zeros(d_ff)
        self.W2 = xavier_init((d_ff, d_model))
        self.b2 = np.zeros(d_model)

        self.dW1 = np.zeros_like(self.W1)
        self.db1 = np.zeros_like(self.b1)
        self.dW2 = np.zeros_like(self.W2)
        self.db2 = np.zeros_like(self.b2)

        self.cache = {}

    def forward(self, x: np.ndarray) -> np.ndarray:
        """
        x shape: (batch, seq, d_model)
        returns shape same as x
        """
        batch, seq, d_model = x.shape
        # First linear
        hidden = x @ self.W1 + self.b1  # (b, seq, d_ff)
        # ReLU
        hidden_relu = np.maximum(hidden, 0)
        # Second linear
        output = hidden_relu @ self.W2 + self.b2  # (b, seq, d_model)

        self.cache = {'x': x, 'hidden': hidden, 'hidden_relu': hidden_relu, 'output': output}
        return output

    def backward(self, dout: np.ndarray) -> np.ndarray:
        """
        dout: (batch, seq, d_model)
        returns dx: (batch, seq, d_model)
        """
        cache = self.cache
        x = cache['x']
        hidden = cache['hidden']
        hidden_relu = cache['hidden_relu']
        output = cache['output']
        batch, seq, d_model = dout.shape

        # dout from output = hidden_relu @ W2 + b2
        # grad w.r.t. hidden_relu
        dhidden_relu = dout @ self.W2.T  # (b, seq, d_ff)
        # grad w.r.t. hidden (ReLU backward)
        dhidden = dhidden_relu * (hidden > 0)
        # grad w.r.t. first linear
        dx = dhidden @ self.W1.T  # (b, seq, d_model)

        # Gradients for weights and biases
        # dW2 = hidden_relu^T @ dout (sum over batch and seq)
        self.dW2 = hidden_relu.reshape(batch * seq, -1).T @ dout.reshape(batch * seq, -1)
        self.db2 = np.sum(dout, axis=(0, 1))
        # dW1 = x^T @ dhidden
        self.dW1 = x.reshape(batch * seq, -1).T @ dhidden.reshape(batch * seq, -1)
        self.db1 = np.sum(dhidden, axis=(0, 1))

        return dx

class TransformerLayer:
    """One transformer encoder layer: self-attention + feed-forward with pre-norm."""
    def __init__(self, d_model: int, n_heads: int, d_ff: int):
        self.attention = MultiHeadAttention(d_model, n_heads)
        self.ff = FeedForward(d_model, d_ff)
        # Layer norm parameters: gamma and beta for each norm
        self.ln1_gamma = np.ones(d_model)
        self.ln1_beta = np.zeros(d_model)
        self.ln2_gamma = np.ones(d_model)
        self.ln2_beta = np.zeros(d_model)

        # For gradients
        self.d_ln1_gamma = np.zeros_like(self.ln1_gamma)
        self.d_ln1_beta = np.zeros_like(self.ln1_beta)
        self.d_ln2_gamma = np.zeros_like(self.ln2_gamma)
        self.d_ln2_beta = np.zeros_like(self.ln2_beta)

        self.cache = {}

    def forward(self, x: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
        # Pre-norm architecture
        x_ln1 = layer_norm(x, self.ln1_g