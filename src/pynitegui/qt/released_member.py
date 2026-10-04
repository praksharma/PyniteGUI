"""Linear-result recovery for PyNite's released member translations."""
import numpy as np
from Pynite.Member3D import Member3D


class ReleasedMember(Member3D):
    @classmethod
    def from_member(cls, member):
        recovered = cls.__new__(cls)
        recovered.__dict__ = member.__dict__.copy()
        recovered._released_displacements = {}
        recovered._solved_combo = None
        return recovered

    def d(self, combo_name="Combo 1"):
        if self.model.solution != "Linear":
            raise ValueError("Released-translation recovery is supported for linear analysis only.")
        if combo_name not in self._released_displacements:
            displacement = super().d(combo_name)
            connected, released = self._partition_D()
            stiffness = self._ke_unc()
            fixed_end = self._fer_unc(combo_name)
            # Recover the eliminated DOFs from zero released-end force using
            # the same uncondensed PyNite matrices as its static condensation.
            displacement[released] = np.linalg.solve(stiffness[np.ix_(released, released)],
                -fixed_end[released] - stiffness[np.ix_(released, connected)] @ displacement[connected])
            if not np.all(np.isfinite(displacement)):
                raise ValueError(f"Member {self.name}: released-end displacement is not finite.")
            self._released_displacements[combo_name] = displacement
        return self._released_displacements[combo_name].copy()


def recover_released_translations(model):
    for physical in model.members.values():
        for name, member in list(physical.sub_members.items()):
            if any(member.Releases[index] for index in (0, 1, 6, 7)):
                recovered = ReleasedMember.from_member(member)
                for combination in model.load_combos:
                    recovered.d(combination)
                physical.sub_members[name] = recovered
