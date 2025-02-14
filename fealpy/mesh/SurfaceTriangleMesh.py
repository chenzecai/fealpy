
import numpy as np
from ..functionspace.lagrange_fem_space import LagrangeFiniteElementSpace
from ..quadrature import TriangleQuadrature
from types import ModuleType
from .mesh_tools import unique_row, find_node, find_entity, show_mesh_2d


class SurfaceTriangleMesh():
    def __init__(self, mesh, surface, p=1, scale=None):
        """
        Initial a object of Surface Triangle Mesh.

        Parameters
        ----------
        self :
            Surface Triangle Mesh Object
        mesh :
            mesh object, represents a triangulation with flat triangle faces.
        surface :
            The continuous surface which was represented as a level set
            function.
        p : int
            The degree of the Lagrange space

        Returns
        -------

        See Also
        --------

        Notes
        -----
        """
        self.mesh = mesh
        self.p = p
        self.space = LagrangeFiniteElementSpace(mesh, p)
        self.surface = surface
        self.ds = mesh.ds

        if scale is None:
            self.node, d = self.surface.project(self.space.interpolation_points())
        else:
            self.node, d = self.surface.project(self.space.interpolation_points()/scale)
            self.node *= scale

        self.ftype = mesh.ftype
        self.itype = mesh.itype
        self.nodedata = {}
        self.celldata = {}

    def integrator(self, k):
        return TriangleQuadrature(k)

    def entity(self, etype=2):
        if etype in ['cell', 2]:
            return self.ds.cell
        elif etype in ['edge', 1]:
            return self.ds.edge
        elif etype in ['node', 0]:
            return self.mesh.node
        else:
            raise ValueError("`entitytype` is wrong!")

    def entity_measure(self, etype=2):
        p = self.p
        if etype in ['cell', 2]:
            return self.area(idx=p+1)
        else:
            raise ValueError("`entitytype` is wrong!")

    def number_of_nodes(self):
        return self.node.shape[0]

    def number_of_edges(self):
        return self.mesh.ds.NE

    def number_of_cells(self):
        return self.mesh.ds.NC

    def geo_dimension(self):
        return self.node.shape[1]

    def top_dimension(self):
        return 2

    def jacobi_matrix(self, bc, cellidx=None):
        mesh = self.mesh
        cell2dof = self.space.dof.cell2dof

        grad = self.space.grad_basis(bc, cellidx=cellidx)
        # the tranpose of the jacobi matrix between S_h and K
        Jh = mesh.jacobi_matrix(cellidx=cellidx)

        # the tranpose of the jacobi matrix between S_p and S_h
        if cellidx is None:
            Jph = np.einsum(
                    'ijm, ...ijk->...imk',
                    self.node[cell2dof, :],
                    grad)
        else:
            Jph = np.einsum(
                    'ijm, ...ijk->...imk',
                    self.node[cell2dof[cellidx], :],
                    grad)

        # the transpose of the jacobi matrix between S_p and K
        Jp = np.einsum('...ijk, imk->...imj', Jph, Jh)
        grad = np.einsum('ijk, ...imk->...imj', Jh, grad)
        return Jp, grad

    def normal(self, bc, cellidx=None):
        Js, _, ps = self.surface_jacobi_matrix(bc, cellidx=cellidx)
        n = np.cross(Js[..., 0, :], Js[..., 1, :], axis=-1)
        return n, ps

    def surface_jacobi_matrix(self, bc, cellidx=None):
        Jp, grad = self.jacobi_matrix(bc, cellidx=cellidx)
        ps = self.bc_to_point(bc, cellidx=cellidx)
        Jsp = self.surface.jacobi_matrix(ps)
        Js = np.einsum('...ijk, ...imk->...imj', Jsp, Jp)
        return Js, grad, ps

    def bc_to_point(self, bc, cellidx=None):
        basis = self.space.basis(bc)
        cell2dof = self.space.dof.cell2dof
        if cellidx is None:
            bcp = np.einsum('...j, ijk->...ik', basis, self.node[cell2dof, :])
        else:
            bcp = np.einsum('...j, ijk->...ik', basis, self.node[cell2dof[cellidx], :])

        bcp, _ = self.surface.project(bcp)
        return bcp

    def area(self, idx=3):
        integrator = self.integrator(idx)
        bcs, ws = integrator.quadpts, integrator.weights
        Jp, _ = self.jacobi_matrix(bcs)
        n = np.cross(Jp[..., 0, :], Jp[..., 1, :], axis=-1)
        l = np.sqrt(np.sum(n**2, axis=-1))
        a = np.einsum('i, ij->j', ws, l)/2.0
        return a

    def add_plot(
            self, plot,
            nodecolor='w', edgecolor='k',
            cellcolor=[0.5, 0.9, 0.45], aspect='equal',
            linewidths=1, markersize=50,
            showaxis=False, showcolorbar=False, cmap='rainbow'):

        if isinstance(plot, ModuleType):
            fig = plot.figure()
            fig.set_facecolor('white')
            axes = fig.gca()
        else:
            axes = plot
        return show_mesh_2d(
                axes, self.mesh,
                nodecolor=nodecolor, edgecolor=edgecolor,
                cellcolor=cellcolor, aspect=aspect,
                linewidths=linewidths, markersize=markersize,
                showaxis=showaxis, showcolorbar=showcolorbar, cmap=cmap)

    def find_node(
            self, axes, node=None,
            index=None, showindex=False,
            color='r', markersize=100,
            fontsize=24, fontcolor='k'):

        if node is None:
            node = self.node

        if (index is None) and (showindex is True):
            index = np.array(range(node.shape[0]))

        find_node(
                axes, node,
                index=index, showindex=showindex,
                color=color, markersize=markersize,
                fontsize=fontsize, fontcolor=fontcolor)

    def find_edge(
            self, axes,
            index=None, showindex=False,
            color='g', markersize=150,
            fontsize=24, fontcolor='k'):

        find_entity(
                axes, self.mesh, entity='edge',
                index=index, showindex=showindex,
                color=color, markersize=markersize,
                fontsize=fontsize, fontcolor=fontcolor)

    def find_cell(
            self, axes,
            index=None, showindex=False,
            color='y', markersize=200,
            fontsize=24, fontcolor='k'):

        find_entity(
                axes, self.mesh, entity='cell',
                index=index, showindex=showindex,
                color=color, markersize=markersize,
                fontsize=fontsize, fontcolor=fontcolor)
