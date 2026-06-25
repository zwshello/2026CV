import argparse
import json
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from torch.utils.data import DataLoader, Dataset


SCRIPT_DIR = Path(__file__).resolve().parent
FILENAME_RE = re.compile(
    r"m(?P<action>\d{2})_s(?P<subject>\d{2})_e(?P<rep>\d{2})_(?P<kind>angles|positions)(?P<incorrect>_inc)?\.txt$"
)

# Kinect joint order from the UI-PRMD paper, Table 2 / Figure 2.
JOINT_NAMES = [
    "waist",
    "spine",
    "chest",
    "neck",
    "head",
    "head_tip",
    "left_collar",
    "left_upper_arm",
    "left_forearm",
    "left_hand",
    "right_collar",
    "right_upper_arm",
    "right_forearm",
    "right_hand",
    "left_upper_leg",
    "left_lower_leg",
    "left_foot",
    "left_leg_toes",
    "right_upper_leg",
    "right_lower_leg",
    "right_foot",
    "right_leg_toes",
]

# Parent indices in the Kinect skeleton tree.
PARENTS = [
    -1,   # waist
    0,    # spine
    1,    # chest
    2,    # neck
    3,    # head
    4,    # head tip
    3,    # left collar
    6,    # left upper arm
    7,    # left forearm
    8,    # left hand
    3,    # right collar
    10,   # right upper arm
    11,   # right forearm
    12,   # right hand
    0,    # left upper leg
    14,   # left lower leg
    15,   # left foot
    16,   # left toes
    0,    # right upper leg
    18,   # right lower leg
    19,   # right foot
    20,   # right toes
]

LEFT_RIGHT_PAIRS = [
    (6, 10),
    (7, 11),
    (8, 12),
    (9, 13),
    (14, 18),
    (15, 19),
    (16, 20),
    (17, 21),
]

SELF_LINKS = [(i, i) for i in range(len(JOINT_NAMES))]
INWARD = [(child, parent) for child, parent in enumerate(PARENTS) if parent >= 0]
OUTWARD = [(parent, child) for child, parent in INWARD]


@dataclass(frozen=True)
class SampleMeta:
    path: Path
    action_id: int
    subject_id: int
    rep_id: int
    correctness: int


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a contrastive multi-stream ST-GCN model on UI-PRMD.")
    parser.add_argument("--data-root", type=Path, default=SCRIPT_DIR / "data" / "UI-PRMD")
    parser.add_argument("--modality", choices=["Kinect"], default="Kinect")
    parser.add_argument("--feature-type", choices=["Positions"], default="Positions")
    parser.add_argument("--sequence-length", type=int, default=96)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=2000)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--dropout", type=float, default=0.35)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--results-root", type=Path, default=SCRIPT_DIR / "results")
    parser.add_argument("--projection-dim", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.10)
    parser.add_argument("--prototype-eps", type=float, default=1e-6)
    parser.add_argument("--early-stop-patience", type=int, default=200)
    parser.add_argument("--threshold-mode", choices=["global", "per-action"], default="per-action")
    parser.add_argument("--disable-mirror-augment", action="store_true")
    return parser.parse_args()


def parse_subject_list(raw: str) -> list[int]:
    values = []
    for token in raw.split(","):
        token = token.strip()
        if token:
            values.append(int(token))
    return values


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    unique = []
    for path in paths:
        path_str = str(path)
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path)
    return unique


def discover_data_roots(data_root: Path) -> list[Path]:
    candidates: list[Path] = []

    if data_root.is_absolute():
        candidates.append(data_root)
    else:
        candidates.append((Path.cwd() / data_root).resolve())
        candidates.append((SCRIPT_DIR / data_root).resolve())
        candidates.append(data_root.resolve())

    base_dirs = [Path.cwd().resolve(), SCRIPT_DIR.resolve()]
    for base_dir in base_dirs:
        candidates.append(base_dir / "data" / "UI-PRMD")
        for parent in [base_dir] + list(base_dir.parents):
            candidates.append(parent / "data" / "UI-PRMD")
            candidates.append(parent / "UI-PRMD")

    for root in [Path("/tmp"), Path("/root")]:
        if not root.exists():
            continue
        try:
            for match in root.rglob("UI-PRMD"):
                if match.is_dir():
                    candidates.append(match)
        except Exception:
            continue

    return _unique_paths([path for path in candidates if path.exists()])


def resolve_feature_dir(
    data_roots: list[Path], movement_dir_name: str, modality: str, feature_type: str
) -> tuple[Path, Path]:
    tried_paths: list[Path] = []
    for data_root in data_roots:
        candidates = [
            data_root / movement_dir_name / movement_dir_name / modality / feature_type,
            data_root / movement_dir_name / modality / feature_type,
        ]
        for candidate in candidates:
            tried_paths.append(candidate)
            if candidate.exists():
                return data_root, candidate

    tried = "\n".join(str(path) for path in _unique_paths(tried_paths))
    raise FileNotFoundError(f"Missing feature directory for {movement_dir_name}. Tried:\n{tried}")


def collect_samples(data_root: Path, modality: str, feature_type: str) -> list[SampleMeta]:
    data_roots = discover_data_roots(data_root)
    if not data_roots:
        raise FileNotFoundError(
            f"Could not resolve any existing UI-PRMD root from --data-root={data_root}. "
            "Please pass --data-root explicitly."
        )

    correct_root, correct_dir = resolve_feature_dir(data_roots, "Segmented Movements", modality, feature_type)
    incorrect_root, incorrect_dir = resolve_feature_dir(data_roots, "Incorrect Segmented Movements", modality, feature_type)

    print(f"[INFO] Using segmented data root: {correct_root}")
    print(f"[INFO] Using incorrect segmented data root: {incorrect_root}")

    samples: list[SampleMeta] = []
    for base_dir, correctness in [(correct_dir, 1), (incorrect_dir, 0)]:
        for path in sorted(base_dir.glob("*.txt")):
            match = FILENAME_RE.match(path.name)
            if not match:
                continue
            samples.append(
                SampleMeta(
                    path=path,
                    action_id=int(match.group("action")) - 1,
                    subject_id=int(match.group("subject")),
                    rep_id=int(match.group("rep")),
                    correctness=correctness,
                )
            )
    if not samples:
        raise RuntimeError("No samples found. Please verify the UI-PRMD directory structure.")
    return samples


def split_samples(
    samples: list[SampleMeta], train_subjects: list[int], val_subjects: list[int], test_subjects: list[int]
) -> tuple[list[SampleMeta], list[SampleMeta], list[SampleMeta]]:
    train_set, val_set, test_set = [], [], []
    train_subjects_set = set(train_subjects)
    val_subjects_set = set(val_subjects)
    test_subjects_set = set(test_subjects)

    overlap = (
        (train_subjects_set & val_subjects_set)
        | (train_subjects_set & test_subjects_set)
        | (val_subjects_set & test_subjects_set)
    )
    if overlap:
        raise ValueError(f"Subject split overlap detected: {sorted(overlap)}")

    for sample in samples:
        if sample.subject_id in train_subjects_set:
            train_set.append(sample)
        elif sample.subject_id in val_subjects_set:
            val_set.append(sample)
        elif sample.subject_id in test_subjects_set:
            test_set.append(sample)

    if not train_set or not val_set or not test_set:
        raise RuntimeError("Train/val/test split is empty. Please adjust subject assignments.")
    return train_set, val_set, test_set


def get_subject_ids(samples: list[SampleMeta]) -> list[int]:
    return sorted({sample.subject_id for sample in samples})


def stratified_holdout_split(
    samples: list[SampleMeta],
    val_ratio: float,
    seed: int,
) -> tuple[list[SampleMeta], list[SampleMeta]]:
    rng = random.Random(seed)
    groups: dict[tuple[int, int], list[SampleMeta]] = {}
    for sample in samples:
        groups.setdefault((sample.action_id, sample.correctness), []).append(sample)

    train_samples: list[SampleMeta] = []
    val_samples: list[SampleMeta] = []
    for group_samples in groups.values():
        shuffled = group_samples[:]
        rng.shuffle(shuffled)
        val_count = max(1, int(round(len(shuffled) * val_ratio)))
        val_samples.extend(shuffled[:val_count])
        train_samples.extend(shuffled[val_count:])
    return train_samples, val_samples


def stratified_k_fold_splits(
    samples: list[SampleMeta],
    num_folds: int,
    seed: int,
) -> list[tuple[list[SampleMeta], list[SampleMeta]]]:
    rng = random.Random(seed)
    groups: dict[tuple[int, int], list[SampleMeta]] = {}
    for sample in samples:
        groups.setdefault((sample.action_id, sample.correctness), []).append(sample)

    fold_val_samples = [[] for _ in range(num_folds)]
    for group_samples in groups.values():
        shuffled = group_samples[:]
        rng.shuffle(shuffled)
        for idx, sample in enumerate(shuffled):
            fold_val_samples[idx % num_folds].append(sample)

    splits = []
    all_set = set(samples)
    for val_samples in fold_val_samples:
        val_set = set(val_samples)
        train_samples = [sample for sample in samples if sample not in val_set]
        splits.append((train_samples, val_samples))
    return splits


def load_raw_sequence(path: Path) -> np.ndarray:
    sequence = np.loadtxt(path, delimiter=",", dtype=np.float32)
    if sequence.ndim == 1:
        sequence = sequence[None, :]
    if sequence.shape[1] != len(JOINT_NAMES) * 3:
        raise ValueError(
            f"Expected {len(JOINT_NAMES) * 3} values per frame for Kinect positions, "
            f"got {sequence.shape[1]} for {path}"
        )
    return sequence.reshape(sequence.shape[0], len(JOINT_NAMES), 3)


def local_to_global_positions(local_positions: np.ndarray) -> np.ndarray:
    global_positions = np.zeros_like(local_positions)
    global_positions[:, 0] = local_positions[:, 0]
    for joint_idx in range(1, len(JOINT_NAMES)):
        parent_idx = PARENTS[joint_idx]
        global_positions[:, joint_idx] = global_positions[:, parent_idx] + local_positions[:, joint_idx]
    return global_positions


def resample_sequence(sequence: np.ndarray, target_len: int) -> np.ndarray:
    if len(sequence) == target_len:
        return sequence.astype(np.float32)
    old_t = np.linspace(0.0, 1.0, num=len(sequence), dtype=np.float32)
    new_t = np.linspace(0.0, 1.0, num=target_len, dtype=np.float32)
    flat = sequence.reshape(len(sequence), -1)
    resized = np.stack([np.interp(new_t, old_t, flat[:, i]) for i in range(flat.shape[1])], axis=1)
    return resized.reshape(target_len, sequence.shape[1], sequence.shape[2]).astype(np.float32)


def normalize_global_positions(global_positions: np.ndarray) -> np.ndarray:
    centered = global_positions - global_positions[:, :1, :]

    bone_lengths = []
    for child, parent in INWARD:
        bone = centered[:, child] - centered[:, parent]
        bone_lengths.append(np.linalg.norm(bone, axis=1))
    bone_lengths = np.stack(bone_lengths, axis=1)
    scale = float(np.clip(bone_lengths.mean(), 1e-6, None))
    return centered / scale


def compute_bone_stream(global_positions: np.ndarray) -> np.ndarray:
    bone = np.zeros_like(global_positions)
    for child, parent in INWARD:
        bone[:, child] = global_positions[:, child] - global_positions[:, parent]
    return bone


def compute_motion_stream(global_positions: np.ndarray) -> np.ndarray:
    return np.diff(global_positions, axis=0, prepend=global_positions[:1])


def mirror_sequence_in_place(sequence: np.ndarray) -> np.ndarray:
    mirrored = sequence.copy()
    mirrored[..., 0] *= -1.0
    for left_idx, right_idx in LEFT_RIGHT_PAIRS:
        mirrored[:, [left_idx, right_idx], :] = mirrored[:, [right_idx, left_idx], :]
    return mirrored


def preprocess_sequence(sequence: np.ndarray, target_len: int, do_mirror: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    global_positions = local_to_global_positions(sequence)
    global_positions = resample_sequence(global_positions, target_len)
    global_positions = normalize_global_positions(global_positions)

    if do_mirror:
        global_positions = mirror_sequence_in_place(global_positions)

    joint_stream = global_positions
    bone_stream = compute_bone_stream(global_positions)
    motion_stream = compute_motion_stream(global_positions)

    return (
        joint_stream.transpose(2, 0, 1).astype(np.float32),
        bone_stream.transpose(2, 0, 1).astype(np.float32),
        motion_stream.transpose(2, 0, 1).astype(np.float32),
    )


class UIPRMDDataset(Dataset):
    def __init__(self, samples: list[SampleMeta], sequence_length: int, mirror_augment: bool):
        self.samples = samples
        self.sequence_length = sequence_length
        self.mirror_augment = mirror_augment

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        sample = self.samples[index]
        sequence = load_raw_sequence(sample.path)
        do_mirror = self.mirror_augment and random.random() < 0.5
        joint_stream, bone_stream, motion_stream = preprocess_sequence(sequence, self.sequence_length, do_mirror)
        return {
            "joint": torch.from_numpy(joint_stream),
            "bone": torch.from_numpy(bone_stream),
            "motion": torch.from_numpy(motion_stream),
            "y": torch.tensor(sample.correctness, dtype=torch.long),
            "action": torch.tensor(sample.action_id, dtype=torch.long),
            "subject": torch.tensor(sample.subject_id, dtype=torch.long),
        }


def normalize_digraph(adj: np.ndarray) -> np.ndarray:
    degree = np.sum(adj, axis=0)
    num_nodes = adj.shape[0]
    degree_matrix = np.zeros((num_nodes, num_nodes), dtype=np.float32)
    for i in range(num_nodes):
        if degree[i] > 0:
            degree_matrix[i, i] = degree[i] ** (-1)
    return adj @ degree_matrix


def edge2mat(edges: list[tuple[int, int]], num_nodes: int) -> np.ndarray:
    mat = np.zeros((num_nodes, num_nodes), dtype=np.float32)
    for dst, src in edges:
        mat[dst, src] = 1.0
    return mat


class Graph:
    def __init__(self):
        num_nodes = len(JOINT_NAMES)
        self.self_links = SELF_LINKS
        self.inward = INWARD
        self.outward = OUTWARD
        self.A = self._build_adjacency(num_nodes)

    def _build_adjacency(self, num_nodes: int) -> np.ndarray:
        identity = edge2mat(self.self_links, num_nodes)
        inward = normalize_digraph(edge2mat(self.inward, num_nodes))
        outward = normalize_digraph(edge2mat(self.outward, num_nodes))
        return np.stack([identity, inward, outward]).astype(np.float32)


class ConvTemporalGraphical(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, num_partitions: int):
        super().__init__()
        self.num_partitions = num_partitions
        self.out_channels = out_channels
        self.conv = nn.Conv2d(in_channels, out_channels * num_partitions, kernel_size=1)

    def forward(self, x: torch.Tensor, adjacency: torch.Tensor) -> torch.Tensor:
        x = self.conv(x)
        n, kc, t, v = x.shape
        x = x.view(n, self.num_partitions, self.out_channels, t, v)
        return torch.einsum("nkctv,kvw->nctw", x, adjacency)


class STGCNBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, kernel_size: tuple[int, int], stride: int, dropout: float, residual: bool):
        super().__init__()
        temporal_kernel_size, spatial_kernel_size = kernel_size
        padding = ((temporal_kernel_size - 1) // 2, 0)
        bottleneck_channels = max(out_channels // 4, 16)

        self.gcn = ConvTemporalGraphical(in_channels, out_channels, spatial_kernel_size)
        self.tcn = nn.Sequential(
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, bottleneck_channels, kernel_size=1),
            nn.BatchNorm2d(bottleneck_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(
                bottleneck_channels,
                bottleneck_channels,
                kernel_size=(temporal_kernel_size, 1),
                padding=padding,
                stride=(stride, 1),
            ),
            nn.BatchNorm2d(bottleneck_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(bottleneck_channels, out_channels, kernel_size=1),
            nn.BatchNorm2d(out_channels),
            nn.Dropout(dropout),
        )

        if not residual:
            self.residual = lambda x: 0
        elif in_channels == out_channels and stride == 1:
            self.residual = nn.Identity()
        else:
            self.residual = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=(stride, 1)),
                nn.BatchNorm2d(out_channels),
            )

        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor, adjacency: torch.Tensor) -> torch.Tensor:
        residual = self.residual(x)
        x = self.gcn(x, adjacency)
        x = self.tcn(x) + residual
        return self.relu(x)


class STGCNBackbone(nn.Module):
    def __init__(self, in_channels: int, adjacency: np.ndarray, dropout: float):
        super().__init__()
        adjacency_tensor = torch.tensor(adjacency, dtype=torch.float32)
        self.register_buffer("A", adjacency_tensor)
        self.data_bn = nn.BatchNorm1d(in_channels * adjacency.shape[1])

        kernel_size = (9, adjacency.shape[0])
        self.blocks = nn.ModuleList(
            [
                STGCNBlock(in_channels, 64, kernel_size, stride=1, dropout=dropout, residual=False),
                STGCNBlock(64, 64, kernel_size, stride=1, dropout=dropout, residual=True),
                STGCNBlock(64, 64, kernel_size, stride=1, dropout=dropout, residual=True),
                STGCNBlock(64, 64, kernel_size, stride=1, dropout=dropout, residual=True),
                STGCNBlock(64, 128, kernel_size, stride=2, dropout=dropout, residual=True),
                STGCNBlock(128, 128, kernel_size, stride=1, dropout=dropout, residual=True),
                STGCNBlock(128, 256, kernel_size, stride=2, dropout=dropout, residual=True),
                STGCNBlock(256, 256, kernel_size, stride=1, dropout=dropout, residual=True),
            ]
        )
        self.edge_importance = nn.ParameterList(
            [nn.Parameter(torch.ones_like(self.A)) for _ in range(len(self.blocks))]
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        n, c, t, v = x.shape
        x = x.permute(0, 3, 1, 2).contiguous().view(n, v * c, t)
        x = self.data_bn(x)
        x = x.view(n, v, c, t).permute(0, 2, 3, 1).contiguous()

        for block, importance in zip(self.blocks, self.edge_importance):
            x = block(x, self.A * importance)

        return x.mean(dim=(2, 3))


class MultiStreamSTGCNClassifier(nn.Module):
    def __init__(self, adjacency: np.ndarray, num_actions: int, dropout: float, projection_dim: int = 128):
        super().__init__()
        self.encoder = STGCNBackbone(in_channels=3, adjacency=adjacency, dropout=dropout)
        self.projection_head = nn.Linear(256, projection_dim)

    def forward(
        self,
        joint_stream: torch.Tensor,
        bone_stream: torch.Tensor,
        motion_stream: torch.Tensor,
        action_ids: torch.Tensor | None = None,
    ) -> torch.Tensor:
        features = self.encoder(joint_stream)
        return F.normalize(self.projection_head(features), dim=1)


def build_dataloaders_from_split(
    train_samples: list[SampleMeta],
    val_samples: list[SampleMeta],
    test_samples: list[SampleMeta],
    args: argparse.Namespace,
) -> tuple[DataLoader, DataLoader, DataLoader, dict[str, int]]:
    train_ds = UIPRMDDataset(
        train_samples,
        args.sequence_length,
        mirror_augment=not args.disable_mirror_augment,
    )
    val_ds = UIPRMDDataset(val_samples, args.sequence_length, mirror_augment=False)
    test_ds = UIPRMDDataset(test_samples, args.sequence_length, mirror_augment=False)

    loader_kwargs = {
        "batch_size": args.batch_size,
        "num_workers": args.num_workers,
        "pin_memory": torch.cuda.is_available(),
    }
    train_loader = DataLoader(train_ds, shuffle=True, **loader_kwargs)
    val_loader = DataLoader(val_ds, shuffle=False, **loader_kwargs)
    test_loader = DataLoader(test_ds, shuffle=False, **loader_kwargs)

    sample_joint = train_ds[0]["joint"].shape
    meta = {
        "in_channels": sample_joint[0],
        "sequence_length": sample_joint[1],
        "num_joints": sample_joint[2],
        "num_actions": len({sample.action_id for sample in train_samples + val_samples + test_samples}),
        "train_size": len(train_ds),
        "val_size": len(val_ds),
        "test_size": len(test_ds),
    }
    return train_loader, val_loader, test_loader, meta


def build_eval_loader(
    samples: list[SampleMeta],
    args: argparse.Namespace,
) -> DataLoader:
    dataset = UIPRMDDataset(samples, args.sequence_length, mirror_augment=False)
    return DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=torch.cuda.is_available(),
    )


def augment_stream_batch(stream: torch.Tensor, noise_std: float, dropout_prob: float) -> torch.Tensor:
    augmented = stream.clone()

    batch_size = augmented.size(0)
    device = augmented.device

    angles = torch.empty(batch_size, device=device).uniform_(-0.17, 0.17)
    shears = torch.empty(batch_size, device=device).uniform_(-0.15, 0.15)
    cos_vals = torch.cos(angles)
    sin_vals = torch.sin(angles)
    transform = torch.zeros(batch_size, 3, 3, device=device, dtype=augmented.dtype)
    transform[:, 0, 0] = cos_vals
    transform[:, 0, 1] = -sin_vals + shears
    transform[:, 1, 0] = sin_vals
    transform[:, 1, 1] = cos_vals
    transform[:, 2, 2] = 1.0
    augmented = torch.einsum("nctv,ncd->ndtv", augmented, transform)

    if noise_std > 0:
        augmented = augmented + torch.randn_like(augmented) * noise_std

    if dropout_prob > 0:
        frame_mask = torch.rand(
            augmented.size(0), 1, augmented.size(2), 1, device=augmented.device
        ) > dropout_prob
        augmented = augmented * frame_mask

    if augmented.size(2) >= 5:
        kernel = torch.tensor([0.25, 0.5, 0.25], device=device, dtype=augmented.dtype).view(1, 1, 3, 1)
        reshaped = augmented.reshape(batch_size * augmented.size(1), 1, augmented.size(2), augmented.size(3))
        blurred = F.conv2d(reshaped, kernel, padding=(1, 0))
        augmented = blurred.reshape_as(augmented)

    scale = torch.empty(augmented.size(0), 1, 1, 1, device=augmented.device).uniform_(0.97, 1.03)
    return augmented * scale


def make_augmented_views(
    joint_stream: torch.Tensor,
    bone_stream: torch.Tensor,
    motion_stream: torch.Tensor,
) -> tuple[tuple[torch.Tensor, torch.Tensor, torch.Tensor], tuple[torch.Tensor, torch.Tensor, torch.Tensor]]:
    view1 = (
        augment_stream_batch(joint_stream, noise_std=0.010, dropout_prob=0.03),
        augment_stream_batch(bone_stream, noise_std=0.010, dropout_prob=0.03),
        augment_stream_batch(motion_stream, noise_std=0.006, dropout_prob=0.03),
    )
    view2 = (
        augment_stream_batch(joint_stream, noise_std=0.015, dropout_prob=0.05),
        augment_stream_batch(bone_stream, noise_std=0.015, dropout_prob=0.05),
        augment_stream_batch(motion_stream, noise_std=0.008, dropout_prob=0.05),
    )
    return view1, view2


def supervised_contrastive_loss(
    embeddings: torch.Tensor,
    action_ids: torch.Tensor,
    correctness: torch.Tensor,
    temperature: float,
) -> torch.Tensor:
    embeddings = F.normalize(embeddings, dim=1)
    similarity = torch.matmul(embeddings, embeddings.T) / temperature

    batch_size = embeddings.size(0)
    eye_mask = torch.eye(batch_size, device=embeddings.device, dtype=torch.bool)
    logits_mask = ~eye_mask

    anchor_mask = correctness == 1
    same_action = action_ids.unsqueeze(0) == action_ids.unsqueeze(1)
    anchor_correct = correctness.unsqueeze(1) == 1
    other_correct = correctness.unsqueeze(0) == 1
    other_incorrect = correctness.unsqueeze(0) == 0

    positive_mask = same_action & anchor_correct & other_correct & logits_mask
    hard_negative_mask = same_action & anchor_correct & other_incorrect & logits_mask
    soft_negative_mask = (~same_action) & anchor_correct & logits_mask
    denominator_mask = hard_negative_mask | soft_negative_mask

    if anchor_mask.sum() == 0:
        return embeddings.new_tensor(0.0)

    logits = similarity - similarity.max(dim=1, keepdim=True).values.detach()
    exp_logits = torch.exp(logits) * denominator_mask.float()
    denom = exp_logits.sum(dim=1, keepdim=True).clamp_min(1e-12)
    log_prob = logits - torch.log(denom)

    positive_counts = positive_mask.sum(dim=1)
    negative_counts = denominator_mask.sum(dim=1)
    valid_anchor_mask = anchor_mask & (positive_counts > 0) & (negative_counts > 0)
    if valid_anchor_mask.sum() == 0:
        return embeddings.new_tensor(0.0)

    loss_per_anchor = -(positive_mask.float() * log_prob).sum(dim=1) / positive_counts.clamp_min(1)
    return loss_per_anchor[valid_anchor_mask].mean()


def run_train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    temperature: float,
) -> dict[str, float]:
    model.train(True)

    total_loss = 0.0
    total_count = 0

    for batch in loader:
        joint_stream = batch["joint"].to(device)
        bone_stream = batch["bone"].to(device)
        motion_stream = batch["motion"].to(device)
        y = batch["y"].to(device)
        action = batch["action"].to(device)

        (joint_v1, bone_v1, motion_v1), (joint_v2, bone_v2, motion_v2) = make_augmented_views(
            joint_stream, bone_stream, motion_stream
        )

        embedding_v1 = model(joint_v1, bone_v1, motion_v1)
        embedding_v2 = model(joint_v2, bone_v2, motion_v2)

        loss = supervised_contrastive_loss(
            torch.cat([embedding_v1, embedding_v2], dim=0),
            torch.cat([action, action], dim=0),
            torch.cat([y, y], dim=0),
            temperature=temperature,
        )

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        total_loss += loss.item() * joint_stream.size(0)
        total_count += joint_stream.size(0)

    return {
        "loss": total_loss / max(total_count, 1),
    }


@torch.no_grad()
def collect_outputs(model: nn.Module, loader: DataLoader, device: torch.device) -> dict[str, np.ndarray]:
    model.eval()
    embeddings: list[np.ndarray] = []
    targets: list[int] = []
    actions: list[int] = []
    subjects: list[int] = []

    for batch in loader:
        joint_stream = batch["joint"].to(device)
        bone_stream = batch["bone"].to(device)
        motion_stream = batch["motion"].to(device)

        embedding = model(joint_stream, bone_stream, motion_stream)
        embeddings.append(embedding.cpu().numpy())
        targets.extend(batch["y"].cpu().tolist())
        actions.extend(batch["action"].cpu().tolist())
        subjects.extend(batch["subject"].cpu().tolist())

    return {
        "embeddings": np.concatenate(embeddings, axis=0),
        "targets": np.array(targets, dtype=np.int64),
        "actions": np.array(actions, dtype=np.int64),
        "subjects": np.array(subjects, dtype=np.int64),
    }


def build_action_prototypes(
    embeddings: np.ndarray,
    actions: np.ndarray,
    targets: np.ndarray,
    num_actions: int,
    eps: float,
) -> dict[int, np.ndarray]:
    prototypes: dict[int, np.ndarray] = {}
    for action_id in range(num_actions):
        mask = (actions == action_id) & (targets == 1)
        if not np.any(mask):
            continue

        action_embeddings = embeddings[mask]
        variance = np.var(action_embeddings, axis=0)
        weights = 1.0 / np.clip(variance, eps, None)
        weights = weights / np.sum(np.abs(weights))
        prototype = weights * np.sum(action_embeddings, axis=0)
        prototypes[action_id] = prototype.astype(np.float32)
    return prototypes


def compute_action_similarities(
    embeddings: np.ndarray,
    actions: np.ndarray,
    prototypes: dict[int, np.ndarray],
) -> np.ndarray:
    similarities = np.full(len(embeddings), -1.0, dtype=np.float32)
    for idx, action_id in enumerate(actions):
        prototype = prototypes.get(int(action_id))
        if prototype is None:
            continue
        denominator = np.linalg.norm(embeddings[idx]) * np.linalg.norm(prototype)
        if denominator <= 1e-12:
            continue
        similarities[idx] = float(np.dot(embeddings[idx], prototype) / denominator)
    return similarities


def optimize_thresholds(
    similarities: np.ndarray,
    actions: np.ndarray,
    targets: np.ndarray,
    num_actions: int,
    mode: str,
) -> dict[int, float]:
    thresholds: dict[int, float] = {}

    if mode == "global":
        valid_mask = similarities > -1.0
        sims = similarities[valid_mask]
        labels = targets[valid_mask]
        candidate_thresholds = sorted(set(float(value) for value in sims.tolist()))
        if not candidate_thresholds:
            return {action_id: 0.0 for action_id in range(num_actions)}
        candidates = [candidate_thresholds[0] - 1e-4] + candidate_thresholds + [candidate_thresholds[-1] + 1e-4]
        best_threshold = candidates[0]
        best_f1 = -1.0
        best_acc = -1.0
        for threshold in candidates:
            preds = (sims >= threshold).astype(np.int64)
            score_f1 = f1_score(labels, preds, average="binary", zero_division=0)
            score_acc = float(np.mean(preds == labels))
            if score_f1 > best_f1 or (score_f1 == best_f1 and score_acc > best_acc):
                best_f1 = score_f1
                best_acc = score_acc
                best_threshold = threshold
        return {action_id: float(best_threshold) for action_id in range(num_actions)}

    for action_id in range(num_actions):
        mask = actions == action_id
        if not np.any(mask):
            continue

        sims = similarities[mask]
        labels = targets[mask]
        candidate_thresholds = sorted(set(float(value) for value in sims.tolist()))
        if not candidate_thresholds:
            thresholds[action_id] = 0.0
            continue

        candidates = [candidate_thresholds[0] - 1e-4] + candidate_thresholds + [candidate_thresholds[-1] + 1e-4]
        best_threshold = candidates[0]
        best_f1 = -1.0
        best_acc = -1.0

        for threshold in candidates:
            preds = (sims >= threshold).astype(np.int64)
            score_f1 = f1_score(labels, preds, average="binary", zero_division=0)
            score_acc = float(np.mean(preds == labels))
            if score_f1 > best_f1 or (score_f1 == best_f1 and score_acc > best_acc):
                best_f1 = score_f1
                best_acc = score_acc
                best_threshold = threshold

        thresholds[action_id] = float(best_threshold)
    return thresholds


def predict_with_prototypes(
    similarities: np.ndarray,
    actions: np.ndarray,
    thresholds: dict[int, float],
) -> list[int]:
    preds = []
    for similarity, action_id in zip(similarities, actions):
        threshold = thresholds.get(int(action_id), 0.0)
        preds.append(int(similarity >= threshold))
    return preds


def evaluate_with_prototypes(
    model: nn.Module,
    prototype_loader: DataLoader,
    eval_loader: DataLoader,
    device: torch.device,
    num_actions: int,
    prototype_eps: float,
    thresholds: dict[int, float] | None = None,
    fit_thresholds: bool = False,
    threshold_mode: str = "per-action",
) -> dict:
    prototype_outputs = collect_outputs(model, prototype_loader, device)
    prototypes = build_action_prototypes(
        prototype_outputs["embeddings"],
        prototype_outputs["actions"],
        prototype_outputs["targets"],
        num_actions=num_actions,
        eps=prototype_eps,
    )

    eval_outputs = collect_outputs(model, eval_loader, device)
    similarities = compute_action_similarities(
        eval_outputs["embeddings"],
        eval_outputs["actions"],
        prototypes,
    )

    if fit_thresholds or thresholds is None:
        thresholds = optimize_thresholds(
            similarities,
            eval_outputs["actions"],
            eval_outputs["targets"],
            num_actions=num_actions,
            mode=threshold_mode,
        )

    preds = predict_with_prototypes(similarities, eval_outputs["actions"], thresholds)
    targets = eval_outputs["targets"].tolist()
    actions = eval_outputs["actions"].tolist()
    subjects = eval_outputs["subjects"].tolist()

    return {
        "targets": targets,
        "preds": preds,
        "actions": actions,
        "subjects": subjects,
        "similarities": similarities.tolist(),
        "prototypes": prototypes,
        "thresholds": thresholds,
        "acc": float(np.mean(np.array(targets) == np.array(preds))),
        "f1": f1_score(targets, preds, average="binary", zero_division=0),
    }


def save_history_plot(history: dict[str, list[float]], output_path: Path) -> None:
    epochs = list(range(1, len(history["train_loss"]) + 1))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].plot(epochs, history["train_loss"], label="Train Loss", linewidth=2)
    axes[0].plot(epochs, history["val_loss"], label="Val Loss", linewidth=2)
    axes[0].set_title("Loss Curve")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].grid(True, linestyle="--", alpha=0.4)
    axes[0].legend()

    axes[1].plot(epochs, history["val_acc"], label="Val Acc", linewidth=2)
    axes[1].plot(epochs, history["val_f1"], label="Val F1", linewidth=2)
    axes[1].set_title("Prototype Validation Accuracy / F1")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Metric")
    axes[1].grid(True, linestyle="--", alpha=0.4)
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def save_confusion_matrix(targets: list[int], preds: list[int], output_path: Path) -> None:
    cm = confusion_matrix(targets, preds, labels=[0, 1])
    plt.figure(figsize=(5, 4))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["Incorrect", "Correct"],
        yticklabels=["Incorrect", "Correct"],
    )
    plt.title("Test Confusion Matrix")
    plt.xlabel("Predicted")
    plt.ylabel("True")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def serialize_args(args: argparse.Namespace) -> dict:
    serialized = {}
    for key, value in vars(args).items():
        if isinstance(value, Path):
            serialized[key] = str(value)
        else:
            serialized[key] = value
    return serialized


def save_json(data: dict | list, output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def serialize_prototypes(prototypes: dict[int, np.ndarray]) -> dict[str, list[float]]:
    return {str(action_id + 1): vector.astype(float).tolist() for action_id, vector in prototypes.items()}


def serialize_thresholds(thresholds: dict[int, float]) -> dict[str, float]:
    return {str(action_id + 1): float(value) for action_id, value in thresholds.items()}


def compute_per_action_metrics(
    targets: list[int],
    preds: list[int],
    actions: list[int],
    num_actions: int,
) -> list[dict]:
    results = []
    targets_arr = np.array(targets)
    preds_arr = np.array(preds)
    actions_arr = np.array(actions)

    for action_id in range(num_actions):
        mask = actions_arr == action_id
        if mask.sum() == 0:
            continue
        action_targets = targets_arr[mask]
        action_preds = preds_arr[mask]
        results.append(
            {
                "action_id": action_id + 1,
                "support": int(mask.sum()),
                "accuracy": float(np.mean(action_targets == action_preds)),
                "f1_correct": float(f1_score(action_targets, action_preds, average="binary", zero_division=0)),
                "f1_incorrect": float(
                    f1_score(1 - action_targets, 1 - action_preds, average="binary", zero_division=0)
                ),
                "correct_support": int((action_targets == 1).sum()),
                "incorrect_support": int((action_targets == 0).sum()),
            }
        )
    return results


def write_per_action_report(per_action_metrics: list[dict], output_path: Path) -> None:
    lines = ["action_id\tsupport\taccuracy\tf1_correct\tf1_incorrect\tcorrect_support\tincorrect_support"]
    for row in per_action_metrics:
        lines.append(
            f"{row['action_id']}\t{row['support']}\t{row['accuracy']:.4f}\t{row['f1_correct']:.4f}\t"
            f"{row['f1_incorrect']:.4f}\t"
            f"{row['correct_support']}\t{row['incorrect_support']}"
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def plot_per_action_metrics(per_action_metrics: list[dict], output_path: Path, title: str) -> None:
    action_ids = [row["action_id"] for row in per_action_metrics]
    accuracies = [row["accuracy"] for row in per_action_metrics]
    f1_scores = [row["f1_correct"] for row in per_action_metrics]

    x = np.arange(len(action_ids))
    width = 0.35
    plt.figure(figsize=(12, 5))
    plt.bar(x - width / 2, accuracies, width=width, label="Accuracy")
    plt.bar(x + width / 2, f1_scores, width=width, label="F1 (Correct)")
    plt.xticks(x, [f"A{action_id}" for action_id in action_ids], rotation=0)
    plt.ylim(0.0, 1.0)
    plt.ylabel("Score")
    plt.title(title)
    plt.grid(True, axis="y", linestyle="--", alpha=0.4)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def plot_fold_metrics(fold_summary_rows: list[dict], output_path: Path) -> None:
    labels = [row["fold_name"] for row in fold_summary_rows]
    accs = [row["test_acc"] for row in fold_summary_rows]
    f1s = [row["test_f1"] for row in fold_summary_rows]

    x = np.arange(len(labels))
    width = 0.35
    plt.figure(figsize=(12, 5))
    plt.bar(x - width / 2, accs, width=width, label="Test Accuracy")
    plt.bar(x + width / 2, f1s, width=width, label="Test F1")
    plt.xticks(x, labels, rotation=0)
    plt.ylim(0.0, 1.0)
    plt.ylabel("Score")
    plt.title("Holdout Performance")
    plt.grid(True, axis="y", linestyle="--", alpha=0.4)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def write_subject_report(fold_summary_rows: list[dict], output_path: Path) -> None:
    lines = ["fold_name\ttrain_subjects\tval_subjects\ttest_subjects\tbest_val_f1\tbest_epoch\ttest_acc\ttest_f1"]
    for row in fold_summary_rows:
        lines.append(
            f"{row['fold_name']}\t{row['train_subjects']}\t{row['val_subjects']}\t{row['test_subjects']}\t"
            f"{row['best_val_f1']:.4f}\t{row['best_epoch']}\t{row['test_acc']:.4f}\t{row['test_f1']:.4f}"
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def train_single_fold(
    fold_name: str,
    train_samples: list[SampleMeta],
    val_samples: list[SampleMeta],
    test_samples: list[SampleMeta],
    args: argparse.Namespace,
    output_dir: Path,
    device: torch.device,
) -> dict:
    train_loader, val_loader, test_loader, meta = build_dataloaders_from_split(
        train_samples, val_samples, test_samples, args
    )
    train_eval_loader = build_eval_loader(train_samples, args)

    graph = Graph()
    model = MultiStreamSTGCNClassifier(
        adjacency=graph.A,
        num_actions=meta["num_actions"],
        dropout=args.dropout,
        projection_dim=args.projection_dim,
    ).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    serialized_args = serialize_args(args)

    history = {
        "train_loss": [],
        "val_loss": [],
        "val_acc": [],
        "val_f1": [],
    }

    best_val_f1 = -1.0
    best_epoch = -1
    epochs_without_improvement = 0
    best_thresholds: dict[int, float] | None = None
    best_prototypes: dict[int, np.ndarray] | None = None

    for epoch in range(1, args.epochs + 1):
        train_metrics = run_train_epoch(
            model,
            train_loader,
            optimizer,
            device,
            temperature=args.temperature,
        )
        val_metrics = evaluate_with_prototypes(
            model,
            prototype_loader=train_eval_loader,
            eval_loader=val_loader,
            device=device,
            num_actions=meta["num_actions"],
            prototype_eps=args.prototype_eps,
            fit_thresholds=True,
            threshold_mode=args.threshold_mode,
        )
        scheduler.step()

        history["train_loss"].append(train_metrics["loss"])
        history["val_loss"].append(1.0 - val_metrics["f1"])
        history["val_acc"].append(val_metrics["acc"])
        history["val_f1"].append(val_metrics["f1"])

        print(
            f"[{fold_name}] Epoch {epoch:03d}/{args.epochs} | "
            f"Contrastive Loss {train_metrics['loss']:.4f} | "
            f"Val Proto Acc {val_metrics['acc']:.4f} F1 {val_metrics['f1']:.4f}"
        )

        if val_metrics["f1"] > best_val_f1:
            best_val_f1 = val_metrics["f1"]
            best_epoch = epoch
            epochs_without_improvement = 0
            best_thresholds = val_metrics["thresholds"]
            best_prototypes = val_metrics["prototypes"]
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "args": serialized_args,
                    "meta": meta,
                    "joint_names": JOINT_NAMES,
                    "parents": PARENTS,
                    "fold_name": fold_name,
                    "thresholds": serialize_thresholds(val_metrics["thresholds"]),
                    "prototypes": serialize_prototypes(val_metrics["prototypes"]),
                },
                output_dir / "best_model.pth",
            )
        else:
            epochs_without_improvement += 1

        if epochs_without_improvement >= args.early_stop_patience:
            print(f"[{fold_name}] Early stopping at epoch {epoch}.")
            break

    torch.save(
        {
            "epoch": len(history["train_loss"]),
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "args": serialized_args,
            "meta": meta,
            "joint_names": JOINT_NAMES,
            "parents": PARENTS,
            "fold_name": fold_name,
            "thresholds": serialize_thresholds(best_thresholds or {}),
            "prototypes": serialize_prototypes(best_prototypes or {}),
        },
        output_dir / "last_model.pth",
    )

    best_ckpt = torch.load(output_dir / "best_model.pth", map_location=device, weights_only=False)
    model.load_state_dict(best_ckpt["model_state_dict"])
    loaded_thresholds = {int(key) - 1: float(value) for key, value in best_ckpt.get("thresholds", {}).items()}

    test_eval = evaluate_with_prototypes(
        model,
        prototype_loader=train_eval_loader,
        eval_loader=test_loader,
        device=device,
        num_actions=meta["num_actions"],
        prototype_eps=args.prototype_eps,
        thresholds=loaded_thresholds,
        fit_thresholds=False,
        threshold_mode=args.threshold_mode,
    )
    test_targets = test_eval["targets"]
    test_preds = test_eval["preds"]
    test_actions = test_eval["actions"]
    test_subjects = test_eval["subjects"]
    test_acc = float(np.mean(np.array(test_targets) == np.array(test_preds)))
    test_f1 = f1_score(test_targets, test_preds, average="binary", zero_division=0)
    report = classification_report(
        test_targets,
        test_preds,
        target_names=["Incorrect", "Correct"],
        digits=4,
        zero_division=0,
    )

    save_history_plot(history, output_dir / "training_curves.png")
    save_confusion_matrix(test_targets, test_preds, output_dir / "confusion_matrix.png")

    per_action_metrics = compute_per_action_metrics(test_targets, test_preds, test_actions, meta["num_actions"])
    write_per_action_report(per_action_metrics, output_dir / "per_action_report.tsv")
    plot_per_action_metrics(per_action_metrics, output_dir / "per_action_metrics.png", f"{fold_name} Per-Action Metrics")

    with open(output_dir / "classification_report.txt", "w", encoding="utf-8") as f:
        f.write(report)
        f.write(f"\nBest validation F1: {best_val_f1:.4f} at epoch {best_epoch}\n")
        f.write(f"Test accuracy: {test_acc:.4f}\n")
        f.write(f"Test F1: {test_f1:.4f}\n")

    save_json(history, output_dir / "history.json")
    save_json(serialize_thresholds(loaded_thresholds), output_dir / "thresholds.json")
    save_json(serialize_prototypes(test_eval["prototypes"]), output_dir / "prototypes.json")

    fold_config = serialized_args.copy()
    fold_config["meta"] = meta
    fold_config["fold_name"] = fold_name
    fold_config["best_val_f1"] = best_val_f1
    fold_config["best_epoch"] = best_epoch
    fold_config["test_acc"] = test_acc
    fold_config["test_f1"] = test_f1
    fold_config["joint_names"] = JOINT_NAMES
    fold_config["parents"] = PARENTS
    fold_config["inference_mode"] = "prototype_similarity_threshold"
    fold_config["thresholds"] = serialize_thresholds(loaded_thresholds)
    save_json(fold_config, output_dir / "run_config.json")

    return {
        "fold_name": fold_name,
        "meta": meta,
        "best_val_f1": best_val_f1,
        "best_epoch": best_epoch,
        "test_acc": test_acc,
        "test_f1": test_f1,
        "targets": test_targets,
        "preds": test_preds,
        "actions": test_actions,
        "subjects": test_subjects,
        "per_action_metrics": per_action_metrics,
        "thresholds": loaded_thresholds,
    }


def main() -> None:
    args = parse_args()
    set_seed(args.seed)

    eval_protocol = "holdout_3_1"
    run_name = f"uiprmd_stgcn_contrastive_proto_{eval_protocol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir = args.results_root / run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    all_samples = collect_samples(args.data_root, args.modality, args.feature_type)
    subject_ids = get_subject_ids(all_samples)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    serialized_args = serialize_args(args)
    all_targets: list[int] = []
    all_preds: list[int] = []
    all_actions: list[int] = []
    fold_summaries: list[dict] = []

    train_samples, val_samples = stratified_holdout_split(all_samples, val_ratio=0.25, seed=args.seed)
    fold_specs: list[dict] = [
        {
            "fold_name": eval_protocol,
            "train_samples": train_samples,
            "val_samples": val_samples,
            "test_samples": val_samples,
            "train_subjects": sorted({sample.subject_id for sample in train_samples}),
            "val_subjects": sorted({sample.subject_id for sample in val_samples}),
            "test_subjects": sorted({sample.subject_id for sample in val_samples}),
        }
    ]

    for fold_spec in fold_specs:
        fold_name = fold_spec["fold_name"]
        fold_dir = output_dir / fold_name
        fold_dir.mkdir(parents=True, exist_ok=True)

        fold_result = train_single_fold(
            fold_name=fold_name,
            train_samples=fold_spec["train_samples"],
            val_samples=fold_spec["val_samples"],
            test_samples=fold_spec["test_samples"],
            args=args,
            output_dir=fold_dir,
            device=device,
        )
        fold_result["train_subjects"] = fold_spec["train_subjects"]
        fold_result["val_subjects"] = fold_spec["val_subjects"]
        fold_result["test_subjects"] = fold_spec["test_subjects"]
        fold_summaries.append(fold_result)
        all_targets.extend(fold_result["targets"])
        all_preds.extend(fold_result["preds"])
        all_actions.extend(fold_result["actions"])

    overall_acc = float(np.mean(np.array(all_targets) == np.array(all_preds)))
    overall_f1 = f1_score(all_targets, all_preds, average="binary", zero_division=0)
    overall_report = classification_report(
        all_targets,
        all_preds,
        target_names=["Incorrect", "Correct"],
        digits=4,
        zero_division=0,
    )
    overall_per_action = compute_per_action_metrics(
        all_targets,
        all_preds,
        all_actions,
        num_actions=fold_summaries[0]["meta"]["num_actions"],
    )

    save_confusion_matrix(all_targets, all_preds, output_dir / "confusion_matrix_overall.png")
    write_per_action_report(overall_per_action, output_dir / "per_action_report_overall.tsv")
    plot_per_action_metrics(overall_per_action, output_dir / "per_action_metrics_overall.png", "Overall Per-Action Metrics")

    fold_summary_rows = []
    for fold in fold_summaries:
        fold_summary_rows.append(
            {
                "fold_name": fold["fold_name"],
                "train_subjects": fold["train_subjects"],
                "val_subjects": fold["val_subjects"],
                "test_subjects": fold["test_subjects"],
                "best_val_f1": fold["best_val_f1"],
                "best_epoch": fold["best_epoch"],
                "test_acc": fold["test_acc"],
                "test_f1": fold["test_f1"],
            }
        )

    with open(output_dir / "summary.txt", "w", encoding="utf-8") as f:
        f.write(overall_report)
        f.write(f"\nOverall accuracy: {overall_acc:.4f}\n")
        f.write(f"Overall F1: {overall_f1:.4f}\n\n")
        f.write(f"Evaluation protocol: {eval_protocol}\n")
        f.write(f"Threshold mode: {args.threshold_mode}\n\n")
        f.write("Fold summaries:\n")
        for row in fold_summary_rows:
            f.write(
                f"{row['fold_name']}: test_subjects={row['test_subjects']}, val_subjects={row['val_subjects']}, "
                f"best_val_f1={row['best_val_f1']:.4f}, best_epoch={row['best_epoch']}, "
                f"test_acc={row['test_acc']:.4f}, test_f1={row['test_f1']:.4f}\n"
            )

    save_json(fold_summary_rows, output_dir / "fold_summaries.json")
    write_subject_report(fold_summary_rows, output_dir / "subject_report.tsv")
    plot_fold_metrics(fold_summary_rows, output_dir / "fold_metrics.png")

    config_to_save = serialized_args.copy()
    config_to_save["eval_protocol"] = eval_protocol
    config_to_save["subjects"] = subject_ids
    config_to_save["joint_names"] = JOINT_NAMES
    config_to_save["parents"] = PARENTS
    config_to_save["overall_acc"] = overall_acc
    config_to_save["overall_f1"] = overall_f1
    config_to_save["inference_mode"] = "prototype_similarity_threshold"
    save_json(config_to_save, output_dir / "run_config.json")

    print("\nTraining finished.")
    print(f"Overall accuracy: {overall_acc:.4f}")
    print(f"Overall F1: {overall_f1:.4f}")
    print(f"Artifacts saved to: {output_dir}")


if __name__ == "__main__":
    main()
