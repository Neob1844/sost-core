"""CGCNN (Crystal Graph Convolutional Neural Network) baseline.

Simplified implementation for Phase II baseline training on small datasets.
Based on: Xie & Grossman, PRL 2018.

This is NOT the full CGCNN — it's a lightweight version suitable for
200-sample datasets on CPU. For production, use the official cgcnn package
or PyTorch Geometric implementations.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import logging

log = logging.getLogger(__name__)


class GaussianExpansion(nn.Module):
    """Expand distances into Gaussian basis functions."""
    def __init__(self, d_min=0.0, d_max=8.0, n_gaussians=40):
        super().__init__()
        centers = torch.linspace(d_min, d_max, n_gaussians)
        self.register_buffer("centers", centers)
        self.width = (d_max - d_min) / n_gaussians

    def forward(self, distances):
        return torch.exp(-((distances.unsqueeze(-1) - self.centers) ** 2) / self.width ** 2)


class CGCNNConv(nn.Module):
    """Single CGCNN convolution layer."""
    def __init__(self, atom_dim, bond_dim):
        super().__init__()
        self.fc_full = nn.Linear(2 * atom_dim + bond_dim, 2 * atom_dim)
        self.ln1 = nn.LayerNorm(2 * atom_dim)
        self.ln2 = nn.LayerNorm(atom_dim)

    def forward(self, atom_feats, bond_feats, nbr_indices):
        N, M = nbr_indices.shape
        # Gather neighbor features
        nbr_feats = atom_feats[nbr_indices.reshape(-1)].reshape(N, M, -1)
        # Concatenate atom, neighbor, bond features
        atom_expand = atom_feats.unsqueeze(1).expand(-1, M, -1)
        combined = torch.cat([atom_expand, nbr_feats, bond_feats], dim=-1)
        combined = combined.reshape(N * M, -1)
        combined = self.ln1(self.fc_full(combined))
        combined = combined.reshape(N, M, -1)
        # Gate mechanism
        half = combined.shape[-1] // 2
        gate = torch.sigmoid(combined[:, :, :half])
        core = F.softplus(combined[:, :, half:])
        # Aggregate over neighbors
        out = (gate * core).mean(dim=1)
        out = self.ln2(out)
        return atom_feats + out  # residual


class CGCNN(nn.Module):
    """Crystal Graph Convolutional Neural Network.

    Lightweight baseline: 2 conv layers, pooling, 2 FC layers.
    """
    def __init__(self, n_elem=94, atom_dim=64, bond_dim=40, n_conv=2, fc_dim=128):
        super().__init__()
        self.embedding = nn.Linear(n_elem, atom_dim)
        self.gaussian = GaussianExpansion(n_gaussians=bond_dim)
        self.convs = nn.ModuleList([CGCNNConv(atom_dim, bond_dim) for _ in range(n_conv)])
        self.fc1 = nn.Linear(atom_dim, fc_dim)
        self.fc2 = nn.Linear(fc_dim, 1)

    def forward(self, atom_feats, bond_dists, nbr_indices):
        # Embed atoms
        x = self.embedding(atom_feats)
        # Expand bond distances
        bond_feats = self.gaussian(bond_dists)
        # Graph convolutions
        for conv in self.convs:
            x = conv(x, bond_feats, nbr_indices)
        # Pool: mean over atoms
        out = x.mean(dim=0, keepdim=True)
        out = F.softplus(self.fc1(out))
        return self.fc2(out).squeeze()
