import numpy as np
import str2keywords
from h5_utilities import *
from scipy.signal import hilbert


def update_fft_axes(axes, forward=True):
    if forward:
        print 'forward transform'
    else:
        print 'backward transform'
    return axes


def analysis(data, ops_list, axes=None):
    """
    Analysis data and change axes accordingly
    
    :param data: array_like data
    :param ops_list: list of operations (str2keywords objects)
    :param axes: list of axes (data_basic_axis objects) pass only the axes that need changes
    :return: return processed data (and axes if provided)  
    """
    for op in ops_list:
        if op == 'abs':
            data = np.abs(data)
        elif op == 'square':
            data = np.square(data)
        elif op == 'sqrt':
            data = np.sqrt(data)
        elif op == 'hilbert_env':
            data = np.abs(hilbert(data))
        elif op == 'fft':
            ax = op.keywords.get('axes', None)
            data = np.fft.fftshift(np.fft.fftn(np.fft.ifftshift(data, axes=ax), **op.keywords), axes=ax)
            if axes is not None:
                dx = axes[1] - axes[0]
                if 'mode_num' in ops_list:
                    axes = np.fft.fftshift(np.fft.fftfreq(len(axes),1./len(axes)))
                else:
                    axes = 2*np.pi*np.fft.fftshift(np.fft.fftfreq(len(axes),dx))
        elif op == 'ifft':
            ax = op.keywords.get('axes', None)
            data = np.fft.ifftshift(np.fft.ifftn(np.fft.fftshift(data, axes=ax), **op.keywords), axes=ax)
        elif op == 'transpose':
            data = np.transpose(data)
        elif op == 'reflect':
            data = np.concatenate((np.flip(data[1:,:],0),data[1:,:]),axis=0)
    if axes is not None:
        return data, axes
    else:
        return data

def reflect(axis, ops_list):
    """
    Reflect axis limits
    
    :param axis: 1D array of length 2
    :param ops_list: list of operations (str2keywords objects)
    :return: return reflected axis
    """
    for op in ops_list:
        if op == 'reflect':
            axis[0] = -axis[-1]
    return axis

# tests
if __name__ == '__main__':
    kw = str2keywords.str2keywords('square')
    a = np.mgrid[:3, :3][0]
    # use ** to unpack the dictionary
    a = analysis(a, [kw])
    print a


def autocorrelate_2d(data,axes=1):
  data_dims = data.shape
  nx = data_dims[0]
  ny = data_dims[1]
  if (axes==0):
      temp=np.zeros(nx)
      for iy in range(0,ny):
        temp=np.correlate(data[:,iy],data[:,iy],mode='full')
        data[:,iy]=temp[temp.size/2:]
  elif (axes==1):
      temp=np.zeros(ny)
      for ix in range(0,nx):
        temp=np.correlate(data[ix,:],data[ix,:],mode='full')
        data[ix,:]=temp[temp.size/2:]

        


