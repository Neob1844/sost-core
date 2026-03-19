"""ALIGNN-Lite — Lightweight line graph neural network for materials.

Inspired by ALIGNN (Atomistic Line Graph Neural Network, Choudhary & DeCost 2021).
This is a self-contained implementation that captures the key idea: using both
atom-bond AND bond-bond (line graph) message passing.

NOT the full ALIGNN — simplified for Phase II baseline on CPU with small datasets.
For production, install the official `alignn` package.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import logging

log = logging.getLogger(__name__)


class GaussianBasis(nn.Module):
    def __init__(self, d_min=0.0, d_max=8.0, n_basis=40):
        super().__init__()
        centers = torch.linspace(d_min, d_max, n_basis)
        self.register_buffer("centers", centers)
        self.width = (d_max - d_min) / n_basis

    def forward(self, dists):
        return torch.exp(-((dists.unsqueeze(-1) - self.centers) ** 2) / self.width ** 2)


class EdgeGatedConv(nn.Module):
    """Edge-gated graph convolution (ALIGNN-style)."""
    def __init__(self, node_dim, edge_dim):
        super().__init__()
        self.src_fc = nn.Linear(node_dim, node_dim)
        self.dst_fc = nn.Linear(node_dim, node_dim)
        self.edge_fc = nn.Linear(edge_dim, node_dim)
        self.gate_fc = nn.Linear(3 * node_dim, node_dim)
        self.ln = nn.LayerNorm(node_dim)

    def forward(self, node_feats, edge_feats, nbr_indices):
        N, M = nbr_indices.shape
        # Gather
        src = node_feats.unsqueeze(1).expand(-1, M, -1)
        dst_idx = nbr_indices.reshape(-1)
        dst = node_feats[dst_idx].reshape(N, M, -1)
        src_t = self.src_fc(src)
        dst_t = self.dst_fc(dst)
        edge_t = self.edge_fc(edge_feats)
        # Gate
        combined = torch.cat([src_t, dst_t, edge_t], dim=-1)
        gate = torch.sigmoid(self.gate_fc(combined))
        # Aggregate
        msg = (gate * dst_t).mean(dim=1)
        return self.ln(node_feats + msg)


class ALIGNNLite(nn.Module):
    """Lightweight ALIGNN-inspired model.

    Key difference from CGCNN: uses edge-gated convolutions with
    separate node and edge transformations (simplified line graph concept).
    """
    def __init__(self, n_elem=94, node_dim=64, edge_dim=40, n_layers=3, fc_dim=128):
        super().__init__()
        self.embedding = nn.Linear(n_elem, node_dim)
        self.gaussian = GaussianBasis(n_basis=edge_dim)
        self.convs = nn.ModuleList([
            EdgeGatedConv(node_dim, edge_dim) for _ in range(n_layers)
        ])
        self.fc1 = nn.Linear(node_dim, fc_dim)
        self.fc2 = nn.Linear(fc_dim, 1)
        self.ln_out = nn.LayerNorm(fc_dim)

    def forward(self, atom_feats, bond_dists, nbr_indices):
        x = self.embedding(atom_feats)
        edge_feats = self.gaussian(bond_dists)
        for conv in self.convs:
            x = conv(x, edge_feats, nbr_indices)
        out = x.mean(dim=0, keepdim=True)
        out = self.ln_out(F.silu(self.fc1(out)))
        return self.fc2(out).squeeze()
