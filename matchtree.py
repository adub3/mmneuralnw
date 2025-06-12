import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.widgets import Button
import pandas as pd
import numpy as np


def load_tournament(file_path: str) -> pd.DataFrame:
    """
    Reads a tournament CSV (with columns TEAM, SEED, CURRENT ROUND, ROUND)
    and returns it as a DataFrame.
    """
    df = pd.read_csv(file_path)
    print(f"Loaded tournament data: {len(df)} rows from {file_path}")
    return df


def filter_by_year(df: pd.DataFrame, year_col: str, year: int) -> pd.DataFrame:
    """
    Filters the DataFrame to only include rows where `year_col` equals `year`.
    """
    print(f"Filtering DataFrame on column '{year_col}' == {year}")
    filtered = df[df[year_col] == year].reset_index(drop=True)
    print(f"Filtered DataFrame has {len(filtered)} rows")
    return filtered

import pandas as pd

def make_matchups(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a DataFrame with columns including:
      - TEAM NO, TEAM, SEED
      - CURRENT ROUND (bracket size: 64,32,…)
      - BY ROUND NO   (ordering within round)
      - SCORE         (points scored in the game)

    Returns a DataFrame with one row per game, including:
      BracketSize,
      TeamNo1, Team1, Seed1, Score1,
      TeamNo2, Team2, Seed2, Score2
    """
    df = df.copy()
    # preserve original row indices for debugging
    df['orig_index'] = df.index
    # sort by game order
    df = df.sort_values('BY ROUND NO').reset_index(drop=True)

    n = len(df)
    if n % 2 != 0:
        raise ValueError(f"Need an even number of rows to pair up, got {n}")

    games = []
    for pos in range(0, n, 2):
        t1 = df.iloc[pos]
        t2 = df.iloc[pos + 1]

        print(
            f"Merging original rows {t1['orig_index']} (TeamNo={t1['TEAM NO']}, "
            f"Team={t1['TEAM']}, Score={t1['SCORE']}) and "
            f"{t2['orig_index']} (TeamNo={t2['TEAM NO']}, Team={t2['TEAM']}, Score={t2['SCORE']})"
        )

        games.append({
            'BracketSize': t1['CURRENT ROUND'],
            'TeamNo1':     t1['TEAM NO'],
            'Team1':       t1['TEAM'],
            'Seed1':       t1['SEED'],
            'Score1':      t1['SCORE'],
            'TeamNo2':     t2['TEAM NO'],
            'Team2':       t2['TEAM'],
            'Seed2':       t2['SEED'],
            'Score2':      t2['SCORE'],
        })

    return pd.DataFrame(games)


class Node:
    def __init__(self,
                 bracket_size,
                 round_num,
                 teamid1, team1, seed1, score1,
                 teamid2, team2, seed2, score2):
        self.bracket_size = bracket_size   # e.g. 2, 4, 8, …
        self.round        = round_num      # slot within that round

        self.teamid1, self.team1,  self.seed1,  self.score1 = (
            teamid1, team1, seed1, score1
        )
        self.teamid2, self.team2,  self.seed2,  self.score2 = (
            teamid2, team2, seed2, score2
        )

        self.left  = None  # first child-game
        self.right = None  # second child-game

    def __repr__(self):
        return (
            f"<Game size={self.bracket_size}"
            f" slot={self.round}: "
            f"{self.team1}(id={self.teamid1},seed={self.seed1})[{self.score1}] vs "
            f"{self.team2}(id={self.teamid2},seed={self.seed2})[{self.score2}]>"
        )



def build_bracket_tree(matchups: pd.DataFrame) -> Node:
    # 1) all round‐sizes in ascending order
    sizes = sorted(matchups['BracketSize'].unique())

    # 2) create a Node for each row, grouped by size
    nodes_by_size = {}
    for size, grp in matchups.groupby('BracketSize'):
        # no more sort_values('Round') here!
        nodes = []
        for slot, (_, row) in enumerate(grp.iterrows(), start=1):
            nodes.append(
                Node(
                    size, slot,
                    row.TeamNo1, row.Team1,  row.Seed1,  row.Score1,
                    row.TeamNo2, row.Team2,  row.Seed2,  row.Score2
                )
            )
        nodes_by_size[size] = nodes

    # 3) link parents → children (exactly as before)
    for i in range(len(sizes) - 1):
        parents  = nodes_by_size[sizes[i]]
        children = nodes_by_size[sizes[i+1]]
        assert len(children) == 2 * len(parents), (
            f"Expected {2*len(parents)} games at size {sizes[i+1]}, "
            f"got {len(children)}"
        )
        for j, parent in enumerate(parents):
            parent.left  = children[2*j]
            parent.right = children[2*j + 1]

    # 4) return the single root game at the smallest size
    return nodes_by_size[sizes[0]][0]


def traverse_preorder(node: Node):
    """Yield every game in preorder (parent → left → right)."""
    yield node
    if node.left:
        yield from traverse_preorder(node.left)
    if node.right:
        yield from traverse_preorder(node.right)


if __name__ == '__main__':
    # — assume you already have `df` loaded and filtered to one year —
    df = pd.read_csv('teamdata/Tournament Matchups.csv')
    df = filter_by_year(df, 'YEAR', 2024)

    # and `df` has exactly one row per game, with columns:
    #   BracketSize, Team1, Seed1, Team2, Seed2
    print(df)
    matchups = make_matchups(df)  # rename if needed
    print(matchups)

    root = build_bracket_tree(matchups)
    # print every round’s games:
    sizes = sorted(matchups['BracketSize'].unique())
    for size in sizes:
        print(f"\n=== Games at bracket size = {size} ===")
        for game in [g for g in traverse_preorder(root) if g.bracket_size == size]:
            print(" ", game)

    # or just do a full preorder walk:
    print("\nFull preorder traversal:")
    for game in traverse_preorder(root):
        print(" ", game)
