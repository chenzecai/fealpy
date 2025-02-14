import numpy as np
from scipy.sparse import coo_matrix, csr_matrix, spdiags
from .function import Function
from ..quadrature import FEMeshIntegralAlg
from timeit import default_timer as timer


class CPPFEMDof3d():
    """
    自由度管理类.
    """
    def __init__(self, mesh, p=1):
        self.mesh = mesh
        self.p = p
        self.cell2dof = self.cell_to_dof()
        self.dpoints = self.interpolation_points()
        self.cell_to_dof_new()

    def multi_index_matrix(self, TD):
        """
        一维和二维的多重指标.
        """
        p = self.p
        if TD == 1:
            ldof = self.number_of_local_dofs()
            multiIndex = np.zeros((ldof, 2), dtype=np.int)
            multiIndex[:, 0] = np.arange(p, -1, -1)
            multiIndex[:, 1] = p - multiIndex[:, 0]
            return multiIndex
        elif TD == 2:
            ldof = (p+1)*(p+2)//2
            idx = np.arange(0, ldof)
            idx0 = np.floor((-1 + np.sqrt(1 + 8*idx))/2)
            multiIndex = np.zeros((ldof, 3), dtype=np.int8)
            multiIndex[:, 2] = idx - idx0*(idx0 + 1)/2
            multiIndex[:, 1] = idx0 - multiIndex[:, 2]
            multiIndex[:, 0] = p - multiIndex[:, 1] - multiIndex[:, 2]
            return multiIndex

    def number_of_local_dofs(self):
        """
        每个单元上的自由度的个数.
        """
        p = self.p
        return (p+1)*(p+1)*(p+2)//2

    def number_of_global_dofs(self):
        """
        全部自由度的个数.
        """

        p = self.p
        mesh = self.mesh
        NN = mesh.number_of_nodes()
        NE = mesh.number_of_edges()
        NTF = mesh.number_of_tri_faces()
        NQF = mesh.number_of_quad_faces()
        NC = mesh.number_of_cells()
        gdof = NN

        if p > 1:
            gdof += NE*(p-1) + NQF*(p-1)*(p-1)

        if p > 2:
            tfdof = (p+1)*(p+2)//2 - 3*p
            gdof += NTF*tfdof
            gdof += NC*tfdof*(p-1)

        return gdof

    def cell_to_dof(self):
        """
        每个单元对应的全局自由度的编号.
        """
        p = self.p
        mesh = self.mesh
        NN = mesh.number_of_nodes()
        NC = mesh.number_of_cells()

        cell = mesh.entity('cell')
        if p == 1:
            return cell
        else:
            ldof = self.number_of_local_dofs()
            w1 = self.multi_index_matrix(1)
            w2 = self.multi_index_matrix(2)
            w3 = np.einsum('ij, km->ijkm', w1, w2)

            w = np.zeros((ldof, 6), dtype=np.int8)
            w[:, 0:3] = w3[:, 0, :, :].reshape(-1, 3)
            w[:, 3:] = w3[:, 1, :, :].reshape(-1, 3)

            ps = np.einsum('im, km->ikm', cell + (NN + NC), w)
            ps.sort()
            t, self.i0, j = np.unique(
                    ps.reshape(-1, 6),
                    return_index=True,
                    return_inverse=True,
                    axis=0)
            return j.reshape(-1, ldof)

    def cell_to_dof_new(self):
        p = self.p
        mesh = self.mesh
        cell = mesh.entity('cell')

        NN = mesh.number_of_nodes()
        NC = mesh.number_of_cells()
        ldof = self.number_of_local_dofs()
        cell2dof = np.zeros((NC, ldof), dtype=np.int)
        idx = np.array([
            0,
            p*(p+1)//2,
            (p+1)*(p+2)//2-1,
            ldof - (p+1)*(p+2)//2,
            ldof - p - 1,
            ldof - 1], dtype=np.int)
        cell2dof[:, idx] = cell

        if p == 1:
            return cell2dof
        else:
            w1 = self.multi_index_matrix(1)
            w2 = self.multi_index_matrix(2)
            w3 = np.einsum('ij, km->ijkm', w1, w2)

            w = np.zeros((ldof, 6), dtype=np.int8)
            w[:, 0:3] = w3[:, 0, :, :].reshape(-1, 3)
            w[:, 3:] = w3[:, 1, :, :].reshape(-1, 3)

            flag = (w != 0)
            isCellIDof = (flag.sum(axis=-1) == 6)
            isNodeDof = (flag.sum(axis=-1) == 1)
            isNewBdDof = ~(isCellIDof | isNodeDof)

            nd = isNewBdDof.sum()
            ps = np.einsum('im, km->ikm', cell + NN + NC, w[isNewBdDof])
            ps.sort()
            _, i0, j = np.unique(
                    ps.reshape(-1, 6),
                    return_index=True,
                    return_inverse=True,
                    axis=0)
            cell2dof[:, isNewBdDof] = j.reshape(-1, nd) + NN

            NB = len(i0)
            nd = isCellIDof.sum()
            if nd > 0:
                cell2dof[:, isCellIDof] = NB + NN + nd*np.arange(NC).reshape(-1, 1) \
                        + np.arange(nd)
            return cell2dof

    def interpolation_points(self):
        p = self.p
        mesh = self.mesh
        cell = mesh.entity('cell')
        node = mesh.entity('node')

        GD = mesh.geo_dimension()

        ldof = self.number_of_local_dofs()
        w1 = self.multi_index_matrix(1)/p
        w2 = self.multi_index_matrix(2)/p
        w3 = np.einsum('ij, km->ijkm', w1, w2)
        w = np.zeros((ldof, 6), dtype=np.float)
        w[:, 0:3] = w3[:, 0, :, :].reshape(-1, 3)
        w[:, 3:] = w3[:, 1, :, :].reshape(-1, 3)
        ps = np.einsum('km, imd->ikd', w, node[cell]).reshape(-1, GD)
        ipoint = ps[self.i0]
        return ipoint


class PrismFiniteElementSpace():

    def __init__(self, mesh, p=1, q=None):
        self.mesh = mesh
        self.p = p

        if q is None:
            self.integrator = mesh.integrator(p+1)
        else:
            self.integrator = mesh.integrator(q)

        self.integralalg = FEMeshIntegralAlg(self.integrator, self.mesh)


    def number_of_global_dofs(self):
        return self.dof.number_of_global_dofs()

    def number_of_local_dofs(self):
        return self.dof.number_of_local_dofs()

    def interpolation_points(self):
        return self.dof.dpoints

    def cell_to_dof(self):
        return self.dof.cell2dof

    def boundary_dof(self):
        return self.dof.boundary_dof()

    def geo_dimension(self):
        return self.GD

    def top_dimension(self):
        return self.TD

    def lagranian_basis(self, bc, TD):
        p = self.p   # the degree of polynomial basis function
        multiIndex = self.dof.multi_index_matrix(TD)
        c = np.arange(1, p+1, dtype=np.int)
        P = 1.0/np.multiply.accumulate(c)
        t = np.arange(0, p)
        shape = bc.shape[:-1]+(p+1, TD+1)
        A = np.ones(shape, dtype=self.ftype)
        A[..., 1:, :] = p*bc[..., np.newaxis, :] - t.reshape(-1, 1)
        np.cumprod(A, axis=-2, out=A)
        A[..., 1:, :] *= P.reshape(-1, 1)
        idx = np.arange(TD+1)
        phi = np.prod(A[..., multiIndex, idx], axis=-1)
        return phi

    def basis(self, bc):
        bc0 = bc[0]
        bc1 = bc[1]
        phi0 = self.lagranian_basis(bc0, 2)
        phi1 = self.lagranian_basis(bc1, 1)
        phi = np.eisum('', phi0, phi1)
        return phi

    def grad_basis(self, bc, cellidx=None):
        pass

    def function(self, dim=None, array=None):
        f = Function(self, dim=dim, array=array)
        return f

    def array(self, dim=None):
        gdof = self.number_of_global_dofs()
        if dim is None:
            shape = gdof
        elif type(dim) is int:
            shape = (gdof, dim)
        elif type(dim) is tuple:
            shape = (gdof, ) + dim
        return np.zeros(shape, dtype=self.ftype)
