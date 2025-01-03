import matplotlib
matplotlib.use('Agg')
import multiprocessing, h5py, sys, glob, os, shutil, subprocess
import numpy as np

from joblib import Parallel, delayed
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib.ticker as ticker
from h5_utilities import *
from analysis import analysis, reflect
import re
from str2keywords import str2keywords
import gc
import colorcet as cc
# global parameters


section_start, section_end, = '{', '}'
ignore_flag, empty, eq_flag, tokenize_flag = '!', '', '=', ','
general_flag, subplot_flag = 'simulation', 'data'
cpu_count = multiprocessing.cpu_count()
times = np.array([])
# match commas not inside single or double quotes
option_pattern = re.compile(''',(?=(?:(?:[^"']*"[^"']*")|(?:[^'"]*'[^'"]*'))*[^"']*$)''')

def mid_norm(im,midpoint=0.0):
    vmin,vmax=im.get_clim()
    cmap=im.get_cmap()
    norm=matplotlib.colors.TwoSlopeNorm(midpoint)
    # newcmp = matplotlib.colors.ListedColormap(cmap(norm(np.linspace(vmin, vmax, int(256*np.max([vmax-midpoint,midpoint-vmin])/(vmax-vmin)/0.5)))))
    newcmp = matplotlib.colors.ListedColormap(cmap(norm(np.linspace(vmin, vmax, 256))))
    im.set_cmap(newcmp)

def make_colormap( cmap_def, name, reg, intrude, power ):
    if name not in plt.colormaps():
        vals = cmap_def(np.arange(cmap_def.N))
        inds = np.arange(reg)
        dat_lower = vals[inds,:]
        dat_lower[:,:3] = np.tile(vals[intrude,:3],(reg,1)) + (1-np.tile(vals[intrude,:3],(reg,1))) * np.power(1-np.tile(inds/reg,(3,1)).T,power)
        cmap_cust = mpl.colors.ListedColormap(np.vstack((dat_lower,vals[intrude:,:])), N=cmap_def.N+reg-intrude, name=name)
        try:
            mpl.colormaps.register(cmap_cust)
        except:
            plt.register_cmap(cmap=cmap_cust)
        cmap_cust = mpl.colors.ListedColormap(np.flip(np.vstack((dat_lower,vals[intrude:,:])),axis=0), N=cmap_def.N+reg-intrude, name=name+'_r')
        try:
            mpl.colormaps.register(cmap_cust)
        except:
            plt.register_cmap(cmap=cmap_cust)

def make_colormap_middle( cmap_def, name, reg, power ):
    if name not in plt.colormaps():
        vals = cmap_def(np.arange(cmap_def.N))
        inds1 = np.arange(int(cmap_def.N/2),int(cmap_def.N/2)+reg)
        vals[inds1,:3] = vals[inds1,:3] + (1-vals[inds1,:3]) * np.power(1-np.tile((inds1-inds1[0])/reg,(3,1)).T,power)
        inds2 = np.arange(int(cmap_def.N/2)-reg,int(cmap_def.N/2))
        vals[inds2,:3] = vals[inds2,:3] + (1-vals[inds2,:3]) * np.power(1-np.tile(np.abs(inds2-inds2[-1])/reg,(3,1)).T,power)
        cmap_cust = mpl.colors.ListedColormap(vals, N=cmap_def.N, name=name)
        try:
            mpl.colormaps.register(cmap_cust)
        except:
            plt.register_cmap(cmap=cmap_cust)
        cmap_cust = mpl.colors.ListedColormap(np.flip(vals,axis=0), N=cmap_def.N, name=name+'_r')
        try:
            mpl.colormaps.register(cmap_cust)
        except:
            plt.register_cmap(cmap=cmap_cust)


def main():
    args = sys.argv
    print('num cores: ' + str(cpu_count))
    file = open(args[1], 'r')
    input_file = file.read()
    file.close()
    # read input deck general parameters
    plots = Plot(input_file)
    dirs = plots.general_dict['save_dir'][0]
    if not os.path.exists(dirs):
        os.makedirs(dirs)
    # else:
    #     shutil.rmtree(dirs)
    #     os.makedirs(dirs)
    dpi = plots.general_dict['dpi'][0]
    fig_size = plots.general_dict['fig_size']
    x, y = dpi * fig_size[0], dpi * fig_size[1]
    if (x * y > 4000 * 2000):
        x, y = x / 2, y / 2

    # read in dla_tracks if desired
    dla_stuff = read_dla_tracks(plots)
    gc.collect()

    plots.parallel_visualize(dla_stuff)

    del(dla_stuff)
    gc.collect()

    if (dirs[len(dirs) - 1] != '/'):
        dirs = dirs + '/'
    stdout = subprocess.check_output(['ffmpeg', '-encoders', '-v', 'quiet'])
    for encoder in [b'libx264', b'mpeg4', b'mpeg']:
        if encoder in stdout:
            break
    else:
        return  # unsupported encoder
    subprocess.call(
        ["ffmpeg", "-framerate", "10", "-pattern_type", "glob", "-i", dirs + '*.png', '-c:v', encoder, '-vf',
         'scale=' + str(x) + ':' + str(y) + ' ,format=yuv420p', '-y', dirs + 'movie.mp4'])


def get_bounds(self, file_name, num, file_num):
    file_name = file_name + f'{num:0{self.sig_0}d}.h5'
    try:
        file = h5py.File(file_name, 'r')
        data = self.get_data(file, file_num)
    except:
        data = read_hdf(file_name).data
    if ('operation' in list(self.general_dict.keys())):
        data = analysis(data, self.general_dict.get('operation'))
    minimum, maximum = np.min(data), np.max(data)
    time = file.attrs['TIME'][0]
    file.close()
    del data
    return minimum, maximum, time


def fmt(x, pos):
    a, b = '{:.2e}'.format(x).split('e')
    b = int(b)
    a = float(a)
    if (a == 0):
        return '0'
    if (a < 0):
        x = '-'
    else:
        x = ''

    return x + '$\mathregular{' + '10^{{{}}}'.format(b) + '}$'


def read_dla_tracks(plots):
    global times
    if (plots.general_dict['dla']):
        sim_dir = plots.general_dict['sim_dir'][0]
        if (len(sim_dir) > 0 and sim_dir[len(sim_dir) - 1] != '/'):
            pref='/'
        else:
            pref=''
        dla_time = np.load(sim_dir+pref+'time'+plots.general_dict['dla_suffix'][0]+'.npy')
        # We only care about the needed times that are after tracking data starts
        times = times[ np.argmax(times>dla_time[0]): ]
        # Resize arrays for comparison
        dla_time_tile = np.tile( dla_time, (times.size,1) )
        times_tile = np.tile( times, (dla_time.size,1) ).T
        # Find the correct indices for the times we want
        inds = np.argmin( np.abs( dla_time_tile - times_tile ), axis=1 )
        # Only keep dla tracking data for the required indices
        dla_time = dla_time[inds]
        dla_data = np.load(sim_dir+pref+'dat'+plots.general_dict['dla_suffix'][0]+'.npy')[:,1:4,inds]
        cumsum = np.load(sim_dir+pref+'cumsum'+plots.general_dict['dla_suffix'][0]+'.npy')[:,:-1,inds]
        return (dla_data,cumsum,dla_time)
    else:
        return None


def visualize(plot, indices, dla_stuff):
    make_colormap( cc.m_rainbow, 'Rainbow', 20, 0, 1.5 )
    make_colormap( cc.m_rainbow4, 'Rainbow4', 20, 0, 1.5 )
    make_colormap( cc.m_bgy, 'BGY', 20, 0, 1.5 )
    make_colormap( cc.m_gouldian, 'Gouldian', 20, 0, 1.5 )
    make_colormap( cc.m_bmw, 'BMW', 20, 0, 1.5 )
    make_colormap( cc.m_bmy, 'BMY', 20, 0, 1.5 )
    make_colormap( cc.m_linear_kry_5_95_c72, 'Fire', 20, 0, 1.5 )
    make_colormap_middle( mpl.cm.jet, 'Jet', 15, 2.0 )
    make_colormap_middle( cc.m_CET_R3, 'Jet2', 15, 2.0 )
    make_colormap_middle( cc.m_CET_D13, 'BG', 10, 2.0 )
    make_colormap_middle( cc.m_CET_D1A, 'BR', 10, 2.0 )
    make_colormap_middle( cc.m_gwv, 'GP', 10, 2.0 )
    make_colormap_middle( cc.m_CET_D3, 'GR', 10, 2.0 )
    make_colormap_middle( cc.m_CET_D10, 'BP', 10, 2.0 )
    make_colormap_middle( cc.m_coolwarm, 'Coolwarm', 10, 2.0 )
    subplots = plot.subplots
    title = ''
    for num in range(len(subplots)):
        height, width = plot.general_dict['fig_size']
        fig = plt.figure(1, figsize=(height, width))
        out_title = subplots[num].graph(fig, indices, num + 1, dla_stuff)
        title = max([title, out_title], key=len)
    plt.suptitle(title, fontsize=plot.general_dict['fontsize'][0] * 1.2)
    plt.tight_layout(rect=[0,0,1,.97])
    fol = plot.general_dict['save_dir'][0]
    if (fol[len(fol) - 1] != '/'):
        fol = fol + '/'
    plt.savefig(fol + str(indices + 1000000)[1:], dpi=plot.general_dict['dpi'][0], bbox_inches='tight')
    plt.close()


class Plot:
    def __init__(self, text):
        # if you want extra parameters at start modify self.types
        self.types = {'subplots': int, 'nstart': int, 'nend': int, 'ndump': int, \
                      'dpi': int, 'fig_size': float, 'fig_layout': int, 'fontsize': int, 'save_dir': str, \
                      'sim_dir': str, 'dla': bool, 'dla_suffix': str, 'cpu_count': int, 't_dec': int}
        # size in inches, dpi for image quality, configuration for plot layouts
        self.laser_params = {}

        self.flag = general_flag
        self.general_keys = list(self.types.keys())
        self.general_dict = {}
        self.subplots = []
        self.read_general_parameters(text, 0)
        self.prep_laser_amp()
        for num in range(self.general_dict['subplots'][0]):
            self.subplots.append(Subplot(text, num, self.general_dict, self.laser_params))

    def read_general_parameters(self, text, ind):
        global cpu_count
        # string = text.lower()
        string = self.find_section(text, ind, self.flag)
        self.read_lines(string)

        # set dla to false if not present
        if ('dla' not in list(self.general_dict.keys())):
            self.general_dict['dla'] = False
        # set dla_suffix to empty string if not present
        if ('dla_suffix' not in list(self.general_dict.keys())):
            self.general_dict['dla_suffix'] = ''
        # set aspect to auto if not present
        if ('aspect' not in list(self.general_dict.keys()) and 'folders' in list(self.general_dict.keys())):
            self.general_dict['aspect'] = ['auto']*len(self.general_dict['folders'])

        # set cpu_count if included
        if 'cpu_count' in self.general_dict.keys():
            cpu_count_in = self.general_dict['cpu_count'][0]
            if cpu_count_in < cpu_count:
                cpu_count = cpu_count_in
                print('Using only {} cores'.format(cpu_count))
            elif cpu_count_in > cpu_count:
                print('{} cores requested, only using the {} cores available'.format(cpu_count_in,cpu_count))

    def find_section(self, text, ind, keyword):
        lines = text.splitlines()
        ind_pas = 0
        start = 0
        end = 0
        for line in lines:
            if (ignore_flag in line):
                curr_line = line[:line.find(ignore_flag)].lower()
            else:
                curr_line = line.lower()
            if (keyword in curr_line):
                if (ind_pas == (ind + 1)):
                    break
                else:
                    ind_pas += 1
            if (ind_pas <= ind):
                start += len(line) + 1
            end += len(line) + 1
        sub_text = text[start:end]
        sub_lines = sub_text.splitlines()
        return sub_text[sub_text.find(section_start):sub_text.rfind(section_end) + 1]

    def read_lines(self, string):
        lines = string.splitlines()
        for line in lines:
            if (ignore_flag in line):
                line = line[:line.find(ignore_flag)]
            for key in self.general_keys:
                if (key in line.split("=")[0].lower()):
                    self.general_dict[key] = self.tokenize_line(line, self.types[key])

    def tokenize_line(self, str, cast_type):
        start = str.find(eq_flag) + 1
        # str = str[start:].split(tokenize_flag)
        str = option_pattern.split(str[start:])
        out = []
        for s in str:
            s = s.strip()
            if (s != empty):
                ele = s.strip("'").strip("\"")
                if (s == 'None' or s == 'none'):
                    out.append('None')
                else:
                    out.append(cast_type(ele))
        return out

    def prep_laser_amp(self):
        # Try gathering the following parameters from the input deck:
        # lon_rise, lon_flat, lon_fall, lon_start, omega0, per_w0, per_focus, a0, dimension
        try:
            with open('os-stdin') as osdata:
                data = osdata.readlines()

            q3d = False

            # Read in all parameters that will be used for calculating the laser amplitude
            for i in range(len(data)):
                if 'quasi-3D' in data[i]:
                    if '!' not in data[i].split("quasi-3D")[0]:
                        q3d = True
                if 'node_number' in data[i]:
                    if q3d:
                        self.laser_params['dimension'] = 3
                    else:
                        self.laser_params['dimension'] = data[i].count(",")
                if 'lon_rise' in data[i]:
                    self.laser_params['lon_rise'] = float(data[i].split("=")[-1].split(",")[0])
                if 'lon_flat' in data[i]:
                    self.laser_params['lon_flat'] = float(data[i].split("=")[-1].split(",")[0])
                if 'lon_fall' in data[i]:
                    self.laser_params['lon_fall'] = float(data[i].split("=")[-1].split(",")[0])
                if 'lon_start' in data[i]:
                    self.laser_params['lon_start'] = float(data[i].split("=")[-1].split(",")[0])
                if 'omega0' in data[i]:
                    self.laser_params['omega0'] = float(data[i].split("=")[-1].split(",")[0])
                if 'per_w0' in data[i]:
                    self.laser_params['per_w0'] = float(data[i].split("=")[-1].split(",")[0])
                if 'per_focus' in data[i]:
                    self.laser_params['per_focus'] = float(data[i].split("=")[-1].split(",")[0])
                if '  a0' in data[i]:
                    self.laser_params['a0'] = float(data[i].split("=")[-1].split(",")[0])
                if 't_rise' in data[i]:
                    self.laser_params['t_rise'] = float(data[i].split("=")[-1].split(",")[0])
                if 't_flat' in data[i]:
                    self.laser_params['t_flat'] = float(data[i].split("=")[-1].split(",")[0])
                if 't_fall' in data[i]:
                    self.laser_params['t_fall'] = float(data[i].split("=")[-1].split(",")[0])
                if 'delay' in data[i]:
                    self.laser_params['delay'] = float(data[i].split("=")[-1].split(",")[0])
                if 'rad_x' in data[i]:
                    self.laser_params['rad_x'] = float(data[i].split("=")[-1].split(",")[0])
                if '  focus' in data[i]:
                    self.laser_params['focus'] = float(data[i].split("=")[-1].split(",")[0])

            if 'delay' not in self.laser_params:
                self.laser_params['delay'] = 0.0

        except:
            pass

    def parallel_visualize(self, dla_stuff):
        global cpu_count
        nstart, ndump, nend = self.general_dict['nstart'], self.general_dict['ndump'], self.general_dict['nend']
        total_num = (np.array(nend) - np.array(nstart)) / np.array(ndump)
        Parallel(n_jobs=cpu_count)(delayed(visualize)(self, nn, dla_stuff) for nn in range( int(np.min(total_num) + 1) ))
        # [visualize(self, nn, dla_stuff) for nn in range( int(np.min(total_num) + 1) )]


class Subplot(Plot):
    def __init__(self, text, num, general_params, laser_params):
        # if you want extra parameters in subplots -- modify self.types
        self.params = general_params
        self.laser_params = laser_params
        self.types = {'folders': str, 'fnames': str, 'title': str, 'log_threshold': float, \
                      'plot_type': str, 'maximum': float, 'minimum': float, \
                      'colormap': str, 'midpoint': float, 'legend': str, 'markers': str, \
                      'x1_lims': float, 'x2_lims': float, 'x3_lims': float, 'rel_lims_x1': float, \
                      'norm': str, 'side': str, 'bounds': str, \
                      'use_dir': str, 'linewidth': float, 'operation': str2keywords, 'transpose': bool, \
                      'x_label': str, 'y_label': str, 'dla_tracks': str, 'fake_cbar': bool, 'fake_annotate': str, \
                      'plot_vac': bool, 'pad': float, 'cblabel': str, 'aspect': str, 'sig_split': str }
        self.left = 0
        self.right = 0
        self.general_dict = {}
        self.raw_edges = {}
        self.file_names = []
        self.general_keys = list(self.types.keys())
        self.flag = subplot_flag
        self.sig_0 = 6
        self.read_general_parameters(text, num)
        self.get_file_names()
        self.count_sides()
        self.set_limits()
        print(self.general_dict)
        print(self.raw_edges)

    def count_sides(self):
        if ('side' in list(self.general_dict.keys())):
            for j in self.general_dict['side']:
                if (j == 'left'):
                    self.left += 1
                else:
                    self.right += 1
        else:
            self.general_dict['side'] = ['left'] * len(self.general_dict['folders'])
            self.left = len(self.general_dict['folders'])
            self.right = 0

    def get_file_names(self):
        folders = self.general_dict['folders']
        if ('fnames' in list(self.general_dict.keys())):
            fnames = self.general_dict['fnames']
        else:
            fnames = ["" for x in range(len(folders))]
        for index in range(len(folders)):
            folder = folders[index]
            if ('use_dir' not in list(self.general_dict.keys()) or (
                (index < len(self.general_dict['use_dir'])) and self.general_dict['use_dir'][index] == 'True')):
                if ('sim_dir' in list(self.params.keys())):
                    if (index < len(self.params['sim_dir'])):
                        sim_dir = self.params['sim_dir'][index]
                    else:
                        if (folder[0:2] == 'MS' or folder[1:3] == 'MS'):
                            sim_dir = self.params['sim_dir'][len(self.params['sim_dir']) - 1]
                        else:
                            sim_dir = ''
                    if (len(sim_dir) > 0 and sim_dir[len(sim_dir) - 1] != '/'):
                        folder = sim_dir + '/' + folder
                    else:
                        folder = sim_dir + folder
            print(folder)
            if (folder[len(folder) - 1] == '/'):
                new2 = glob.iglob(folder + '*' + fnames[index] + '*.h5')
            else:
                new2 = glob.iglob(folder + '/*' + fnames[index] + '*.h5')
            first = next(new2)
            if 'sig_split' in list(self.general_dict.keys()):
                sig_split = self.general_dict['sig_split'][index]
            else:
                sig_split = "-"
            self.sig_0 = len(first.split(sig_split)[-1]) - 3
            first = first[:len(first) - self.sig_0 - 3]  # removes 000000.h5
            self.file_names.append(first)

    def get_nfac(self, index):
        if (index < len(self.params['nstart'])):
            return self.params['nstart'][index], self.params['ndump'][index], self.params['nend'][index]
        else:
            last_ind = len(self.params['nstart']) - 1
            return self.params['nstart'][last_ind], self.params['ndump'][last_ind], self.params['nend'][last_ind]

    def set_limits(self):
        global cpu_count, times
        folders = self.general_dict['folders']
        subplot_keys = list(self.general_dict.keys())
        minimum, maximum = None, None
        min_max_pairs = []
        if times.size==0:
            # Only works when reading from one folder at a time
            nstart, ndump, nend = self.get_nfac(0)
            times = np.zeros(len(np.arange(nstart, nend + 1, ndump)))

        for index in range(len(folders)):
            if (self.get_indices(0)[0]=='slice_contour' and index>0):
                break
            nstart, ndump, nend = self.get_nfac(index)

            out = Parallel(n_jobs=cpu_count)(
                delayed(get_bounds)(self, self.file_names[index], nn, index) for nn in range(nstart, nend + 1, ndump))
            # out = [get_bounds(self, self.file_names[index], nn, index) for nn in range(nstart, nend + 1, ndump)]
            print([i[0:2] for i in out])
            for i, (mn, mx, time) in enumerate(out):
                if (maximum == None):
                    maximum = mx
                else:
                    if (mx > maximum):
                        maximum = mx
                if (minimum == None):
                    minimum = mn
                else:
                    if (mn < minimum):
                        minimum = mn
                times[i] = time
            min_max_pairs.append((minimum, maximum))
            maximum, minimum = None, None
        mins, maxs = [np.inf, np.inf], [-np.inf, -np.inf]
        for file_num in range(len(folders)):
            if (self.get_indices(0)[0]=='slice_contour' and file_num>0):
                break
            mn, mx = min_max_pairs[file_num]
            if (self.general_dict['side'][file_num] == 'left'):
                mins[0] = min(mins[0], mn)
                maxs[0] = max(maxs[0], mx)
            else:
                mins[1] = min(mins[1], mn)
                maxs[1] = max(maxs[1], mx)
        if ('maximum' in list(self.general_dict.keys())):
            for ind in range(len(self.general_dict['maximum'])):
                if (self.general_dict['maximum'][ind] != 'None'):
                    if (self.general_dict['side'][ind] == 'left'):
                        maxs[0] = self.general_dict['maximum'][ind]
                    else:
                        maxs[1] = self.general_dict['maximum'][ind]
        if ('minimum' in list(self.general_dict.keys())):
            for ind in range(len(self.general_dict['minimum'])):
                if (self.general_dict['minimum'][ind] != 'None'):
                    if (self.general_dict['side'][ind] == 'left'):
                        mins[0] = self.general_dict['minimum'][ind]
                    else:
                        mins[1] = self.general_dict['minimum'][ind]

        self.general_dict['minimum'] = mins
        self.general_dict['maximum'] = maxs
        print(mins, maxs)

    def get_min_max(self, file_num):
        if (self.general_dict['side'][file_num] == 'left'):
            return self.general_dict['maximum'][0], self.general_dict['minimum'][0]
        else:
            return self.general_dict['maximum'][1], self.general_dict['minimum'][1]

    def get_x_lims(self, ax, curr_lims=None):
        if (ax+'_lims' in list(self.general_dict.keys())):
            lims = np.zeros(2)
            for ind in range(len(self.general_dict[ax+'_lims'])):
                lims[ind] = self.general_dict[ax+'_lims'][ind]
            return lims
        elif ('rel_lims_'+ax in list(self.general_dict.keys())):
            if curr_lims is None:
                print("When using 'rel_lims_"+ax+"', curr_lims must be provided")
                print("to the get_x_lims function")
                sys.exit("Exiting program")
            lims = np.zeros(2)
            for ind in range(len(self.general_dict['rel_lims_'+ax])):
                lims[ind] = curr_lims[ind] + self.general_dict['rel_lims_'+ax][ind]
            return lims
        else:
            return None

    def graph(self, figure, n_ind, subplot_num, dla_stuff):
        fig = figure
        rows, columns = self.params['fig_layout']
        ax_l = plt.subplot(rows, columns, subplot_num)
        ax = ax_l
        time = r'$ t = '

        plot_prev = None
        len_file_names = 0
        for j in range(2):
            if (j == 0):
                key = 'left'
            else:
                key = 'right'
                if (self.right == 0):
                    break
                else:
                    ax = ax_l.twinx()
            for file_num in range(len(self.file_names)):
                if (self.general_dict['side'][file_num] == key):
                    nstart, ndump, nend = self.get_nfac(file_num)
                    nn = ndump * n_ind + nstart
                    file = h5py.File(self.file_names[file_num] + f'{nn:0{self.sig_0}d}.h5', 'r')
                    plot_type = self.get_indices(file_num)[0]

                    if (plot_type == 'slice'):
                        self.plot_grid(file, file_num, ax, fig)
                        if ('dla_tracks' in list(self.general_dict.keys())):
                            # dla_data, cumsum, dla_time = dla_stuff
                            if (file.attrs['TIME'][0] >= dla_stuff[2][0]):
                                ind=np.argmin(np.abs(dla_stuff[2]-file.attrs['TIME'][0]))
                                clbl = '$W_{DLA}-W_{LWFA}$ [MeV]'

                                if self.general_dict['dla_tracks'][0] == 'old':
                                    # Use old method, where cumsum was just [wake, dla, total]
                                    c_dat = dla_stuff[1][:,1,ind] - dla_stuff[1][:,0,ind]
                                    y_dat = dla_stuff[0][:,1,ind]

                                elif self.general_dict['dla_tracks'][0] == 'total':
                                    # Use current method for 2D/3D, where cumsum is [wake, dla2, dla3, total]
                                    c_dat = np.sum(dla_stuff[1][:,1:3,ind],axis=1) - dla_stuff[1][:,0,ind]
                                    y_dat = dla_stuff[0][:,1,ind]

                                elif self.general_dict['dla_tracks'][0] == 'transverse':
                                    # Use current method for q3D transverse, where cumsum is [wake, dla2, dla3, total]
                                    # Plot component if requested
                                    if len(self.general_dict['dla_tracks'])==2:
                                        comp = int(self.general_dict['dla_tracks'][1])
                                        c_dat = dla_stuff[1][:,comp-1,ind]
                                        clbl = '$W_{E_'+str(comp)+'}$ [MeV]'
                                    else:
                                        c_dat = np.sum(dla_stuff[1][:,1:3,ind],axis=1) - dla_stuff[1][:,0,ind]
                                    y_dat = np.sqrt(np.sum(np.square(dla_stuff[0][:,1:3,ind]),axis=1))

                                elif self.general_dict['dla_tracks'][0] == 'modal':
                                    # Use q3D modal, where cumsum is [wake1, wake2, wake3, dla1, dla2, dla3, total]
                                    # Plot component if requested
                                    if len(self.general_dict['dla_tracks'])==2:
                                        comp = int(self.general_dict['dla_tracks'][1])
                                        c_dat = dla_stuff[1][:,comp-1,ind]
                                        clbl = '$W_{E_'+str((comp-1)%3+1)+',m='+str((comp-1)//3)+'}$ [MeV]'
                                    else:
                                        c_dat = np.sum(dla_stuff[1][:,3:6,ind],axis=1) - np.sum(dla_stuff[1][:,0:3,ind],axis=1)
                                    y_dat = np.sqrt(np.sum(np.square(dla_stuff[0][:,1:3,ind]),axis=1))

                                else:
                                    try:
                                        comp = int(self.general_dict['dla_tracks'])
                                        c_dat = dla_stuff[1][:,comp-1,ind]
                                        y_dat = dla_stuff[0][:,1,ind]
                                        clbl = '$W_{E_'+str(comp)+'}$ [MeV]'
                                    except:
                                        print("Invalid value for 'dla_tracks'")
                                        print("Valid values are 'old', 'total', 'transverse', 'modal', or an integer")
                                        sys.exit("Exiting program")

                                axd2=plt.scatter(dla_stuff[0][:,0,ind],y_dat,s=4,c=c_dat,cmap='PiYG')
                                mid_norm( axd2, midpoint=0 )

                                divider = make_axes_locatable(plt.gca())
                                cax2 = divider.new_horizontal(size="5%", pad=0.7, pack_start=True)
                                fig.add_axes(cax2)
                                cb2 = fig.colorbar(axd2,cax=cax2)
                                cb2.ax.yaxis.set_ticks_position('left')
                                cb2.set_label(clbl)
                                cb2.ax.yaxis.set_label_position('left')
                    elif (plot_type == 'raw'):
                        self.plot_raw(file, file_num, ax, fig)
                    elif (plot_type == 'lineout'):
                        self.plot_lineout(file, file_num, ax, fig)
                    elif (plot_type == 'slice_contour'):
                        if file_num == 0:
                            self.plot_grid(file, file_num, ax, fig)
                            nstart, ndump, nend = self.get_nfac(file_num+1)
                            nn = ndump * n_ind + nstart
                            file2 = h5py.File(self.file_names[file_num+1] + f'{nn:0{self.sig_0}d}.h5', 'r')
                            self.plot_contour(file, file2, file_num, ax, fig)
                            if 't_dec' in list(self.params.keys()):
                                time_str = file.attrs['TIME'][0]
                                sig_figs = self.params['t_dec'][0]
                                time = time + f'{time_str:.{sig_figs}f}'
                            else:
                                time = time + str(file.attrs['TIME'][0])
                            file.close()
                            file2.close()
                            break

                    plot_prev = plot_type
                    if 't_dec' in list(self.params.keys()):
                        time_str = file.attrs['TIME'][0]
                        sig_figs = self.params['t_dec'][0]
                        time = time + f'{time_str:.{sig_figs}f}'
                    else:
                        time = time + str(file.attrs['TIME'][0])
                    if (file_num < len(self.file_names) - 1):
                        time = time + ','
                    file.close()
            if (not plot_type == 'slice_contour'):
                self.set_legend(key, ax)

        time = time + '$'
        return time

    def set_legend(self, key, ax):
        select = {'left': self.left, 'right': self.right}
        num_on_axis = select[key]
        if (num_on_axis > 1):
            ax.legend()
            # if (key == 'right'):
            #     ax.legend(loc=1)
            # else:
            #     ax.legend(loc=2)

    def add_colorbar(self, imAx, label_, ticks, file_num, ax, fig):
        if ('pad' in list(self.general_dict.keys())):
            pad = self.general_dict['pad'][file_num]
        else:
            pad = 0.075
        if ('cblabel' in list(self.general_dict.keys())):
            label = self.general_dict['cblabel'][file_num]
        else:
            label = label_
        plt.minorticks_on()
        # divider = make_axes_locatable(ax)
        # cax = divider.append_axes("right", size="2%", pad=0.05)
        # plt.colorbar(imAx,cax=cax,format='%.1e')
        # ax.minorticks_on()
        # divider = make_axes_locatable(ax)
        # cax = divider.append_axes("right", size="2%", pad=0.05)
        if (ticks == None):
            cb = fig.colorbar(imAx, pad=pad)
            cb.set_label(label, fontsize=self.fontsize())
            cb.ax.tick_params(labelsize=self.fontsize())
            cb.formatter.set_powerlimits((0, 0))
            cb.ax.yaxis.offsetText.set(size=self.fontsize())
            # cb.locator = mpl.ticker.MaxNLocator(nbins=5)
            cb.update_ticks()
        else:
            cb = fig.colorbar(imAx, pad=pad, ticks=ticks, format=ticker.FuncFormatter(fmt))
            cb.set_label(label, fontsize=self.fontsize())
            cb.ax.tick_params(labelsize=self.fontsize())



        # cb.ticklabel_format(style='sci', scilimits=(0,0))

    def mod_tickers(self, minimum, maximum, threshold):
        out = []
        epsilon = 1e-30
        mu = int(np.log10(np.abs(maximum + epsilon))) + 1
        mx_sign, mn_sign = 1, -1
        if (maximum < 0):
            mx_sign = mx_sign * -1
        if (minimum > 0):
            mn_sign = mn_sign * -1
        ml = int(np.log10(threshold)) - 1
        ll = int(np.log10(np.abs(minimum + epsilon))) + 1
        dx = -1
        if (ll - ml > 4):
            dx = -2
        for j in range(ll, ml, dx):
            out.append(mn_sign * 10 ** (j))
        out.append(0)
        dx = 1
        if (mu - ml > 4):
            dx = 2
        for j in range(ml + 1, mu + 1, dx):
            out.append(mx_sign * 10 ** (j))
        return out

    def get_indices(self, file_num):
        ctr = 0
        index = 0
        index_start = 0
        plot_types = self.general_dict['plot_type']
        while (True):
            if (index == len(plot_types)):
                break
            if (plot_types[index].lower() in ['slice', 'lineout', 'raw', 'slice_contour']):
                if (ctr == (file_num + 1)):
                    break
                ctr += 1
                index_start = index
            index += 1
        return self.general_dict['plot_type'][index_start:index]

    def get_data(self, file, file_num):

        indices = self.get_indices(file_num)
        if (len(indices) > 1):
            selectors = indices[1:]
        else:
            selectors = None
        plot_type = indices[0]
        axis_labels = []
        if ('axes' not in list(self.general_dict.keys())):
            self.general_dict['axes'] = []
        if (plot_type == 'slice' or plot_type == 'lineout' or plot_type == 'slice_contour'):
            axes = file['AXIS']
            for j in list(axes.keys()):
                axis_labels.append(axes[j].attrs['NAME'][0].decode('utf-8'))

            if (selectors == None):
                self.general_dict['axes'].extend(axis_labels)
                try:
                    data = (file[file.attrs['NAME'][0]][:])
                except:
                    data = (file[list(file)[-1]][:])
                return data

        if (plot_type == 'slice' or plot_type == 'slice_contour'):
            axis_labels.remove(selectors[0])
            self.general_dict['axes'].extend(axis_labels)
            try:
                data = (file[file.attrs['NAME'][0]][:])
            except:
                data = (file[list(file)[-1]][:])
            if (selectors[0] == 'x1'):
                return data[:, :, int(selectors[1])]
            elif (selectors[0] == 'x2'):
                return data[:, int(selectors[1]), :]
            else:
                return data[int(selectors[1]), :, :]

        if (plot_type == 'lineout'):
            self.general_dict['axes'].append(selectors[0])
            try:
                data = (file[file.attrs['NAME'][0]][:])
            except:
                data = (file[list(file)[-1]][:])
            if (len(selectors) == 3):
                x2_ind, x3_ind = int(selectors[1]), int(selectors[2])
                if (selectors[0] == 'x1'):
                    return data[x3_ind, x2_ind, :]
                elif (selectors[0] == 'x2'):
                    return data[x3_ind, :, x2_ind]
                else:
                    return data[:, x3_ind, x2_ind]
            else:
                x2_ind = int(selectors[1])
                if (selectors[0] == 'x1'):
                    return data[x2_ind, :]
                else:
                    return data[:, x2_ind]
        if (plot_type == 'raw'):
            bins = int(selectors[-1])
            if (len(self.general_dict['axes']) <= file_num):
                self.general_dict['axes'].extend(selectors[:-1])
            dim = len(selectors[:-1])
            if (len(file['q'].shape) == 0):
                print(file['q'].shape)
                if (dim == 2):
                    self.raw_edges[file_num] = [np.zeros(1), np.zeros(1)]
                    return np.zeros(1)
                else:
                    self.raw_edges[file_num] = [np.zeros(1)]
                    return np.zeros(1)

            q_weight = file['q'][:]
            nx = file.attrs['NX'][:]
            dx = (file.attrs['XMAX'][:] - file.attrs['XMIN'][:]) / (nx)
            if ('norm' in list(self.general_dict.keys()) and file_num < len(self.general_dict['norm']) and
                        self.general_dict['norm'][file_num] == 'cylin'):
                norm = np.pi * 2 * np.prod(dx)
            else:
                norm = np.prod(dx)
            print(np.sum(q_weight * norm), 'charge', self.file_names[file_num], norm)
            print(len(q_weight), 'length')
            if (dim == 2):
                if (selectors[0] == 'r'):
                    data1 = ((file['x2'][:]) ** 2 + (file['x3'][:]) ** 2) ** (0.5)
                else:
                    data1 = file[selectors[0]][:]
                if (selectors[1] == 'r'):
                    data2 = ((file['x2'][:]) ** 2 + (file['x3'][:]) ** 2) ** (0.5)
                else:
                    data2 = file[selectors[1]][:]
                bounds1 = self.get_bounds(selectors[0])
                bounds2 = self.get_bounds(selectors[1])
                if (bounds1 == None or bounds2 == None):
                    bounds = None
                else:
                    bounds = [bounds1, bounds2]
                hist, yedges, xedges = np.histogram2d(data1, data2, bins=bins, range=bounds,
                                                      weights=np.abs(q_weight * norm))
                xedges, yedges = (xedges[1:] + xedges[:-1]) / 2.0, (yedges[1:] + yedges[:-1]) / 2.0
                self.raw_edges[file_num] = [xedges, yedges]
            else:
                if (selectors[0] == 'r'):
                    data1 = ((file['x2'][:]) ** 2 + (file['x3'][:]) ** 2) ** (0.5)
                else:
                    data1 = file[selectors[0]]
                bounds = self.get_bounds(selectors[0])
                hist, bin_edges = np.histogram(data1, bins=bins, range=bounds, weights=np.abs(q_weight * norm))
                bin_edges = (bin_edges[1:] + bin_edges[:-1]) / 2.0
                self.raw_edges[file_num] = [bin_edges]
            return hist

    def append_legend(self, file_num):
        if ('legend' in list(self.general_dict.keys()) and file_num < len(self.general_dict['legend'])):
            return r'${}$'.format(self.general_dict['legend'][file_num])
        else:
            return ''

    def get_bounds(self, label):
        if ('bounds' in list(self.general_dict.keys()) and label in self.general_dict['bounds']):
            bounds = self.general_dict['bounds']
            index = bounds.index(label) + 1
            return map(float, bounds[index:(index + 2)])
        else:
            return None

    def plot_lineout(self, file, file_num, ax, fig):
        try:
            data = self.get_data(file, file_num)
        except:
            data = read_hdf(file.filename).data
        axes = self.get_axes(file_num)
        xx = self.construct_axis(file, axes[0], file_num)
        if ('operation' in list(self.general_dict.keys())):
            data,xx = analysis(data, self.general_dict['operation'], axes1=xx)
        maximum, minimum = self.get_min_max(file_num)
        indices = self.get_indices(file_num)
        selectors = indices[1:-1]
        if (indices[0].lower() == 'raw'):
            label = self.get_name(file, 'q') + self.append_legend(file_num)
        else:
            label = self.get_name(file) + self.append_legend(file_num)

        if (self.is_log_plot(file_num)):
            l, = ax.plot(xx, data, self.get_marker(file_num), label=label, linewidth=self.get_linewidth())
            side = self.general_dict['side'][file_num]
            if (side == 'left'):
                ind = 0
            else:
                ind = 1
            threshold = self.general_dict['log_threshold'][ind]
            plt.yscale('symlog', linthresh=threshold)
            ax.set_ylim([minimum, maximum])

        else:
            l, = ax.plot(xx, data, self.get_marker(file_num), label=label, linewidth=self.get_linewidth())
            ax.set_ylim([minimum, maximum])
            ax.minorticks_on()
            plt.ticklabel_format(style='sci', axis='y', scilimits=(0, 0))

        if ('operation' in list(self.general_dict.keys())):
            for op in self.general_dict['operation']:
                if op == 'hilbert_env':
                    if ('plot_vac' in list(self.general_dict.keys())):
                        if self.general_dict['plot_vac']:
                            zpulse_keys = ["lon_rise","lon_flat","lon_fall","lon_start","per_w0","per_focus"]
                            antenna_keys = ["t_rise","t_flat","t_fall","delay","rad_x","focus"]
                            if all([k in self.laser_params for k in zpulse_keys]) or \
                               all([k in self.laser_params for k in antenna_keys]):
                               lsr_amp = self.laser_amp(xx,file.attrs['TIME'][0])
                               ax.plot(xx, lsr_amp, '--', label='vacuum', linewidth=self.get_linewidth() )
                               plt.ylim(top=np.max([maximum,lsr_amp.max()]))

        ax.set_xlim(self.get_x_lims('x1',curr_lims=[np.min(xx),np.max(xx)]))
        if self.get_x_lims('x1',curr_lims=[np.min(xx),np.max(xx)]) is None:
            ax.set_xlim([np.min(xx),np.max(xx)])

        self.set_labels(ax, file, axes, file_num)

        plt.title(self.general_dict['title'][file_num],fontsize = self.fontsize())

        if ('fake_cbar' in list(self.general_dict.keys())):
            if self.general_dict['fake_cbar']:
                sm = plt.cm.ScalarMappable(cmap='viridis', norm=plt.Normalize(vmin=0, vmax=1))
                cb=plt.colorbar(sm, ax=plt.gca())
                cb.set_label('Hi')
                cb.remove()

        if ('fake_annotate' in list(self.general_dict.keys())):
            plt.annotate(self.general_dict['fake_annotate'],(0.5,0.5),(1.01,0.5), xycoords=plt.gca().transAxes, textcoords=plt.gca().transAxes, color='w')

    def get_linewidth(self):
        if ('linewidth' in list(self.general_dict.keys())):
            return self.general_dict['linewidth'][0]
        else:
            return 1

    def laser_amp(self, z, t):

        def fenv(tt):
            return 10 * np.power(tt,3) - 15 * np.power(tt,4) + 6 * np.power(tt,5)

        d = self.laser_params

        if 'lon_rise' in d:
            # Calculate fields based on zpulse
            length = d['lon_rise'] + d['lon_flat'] + d['lon_fall']
            x = d['lon_start'] + t - z
            inds = [ x<length, x<d['lon_rise']+d['lon_flat'], x<d['lon_rise'], x<0.0 ]

            # Piecewise function done in reverse order of if else to make the last one true
            lon_envelope = np.piecewise( x, inds, [ fenv( (length-x[inds[0]])/d['lon_fall'] ), 1.0, 
                                                    fenv(x[inds[2]]/d['lon_rise']), 0.0, 0.0] )

            z0 = d['omega0'] * np.square(d['per_w0']) / 2
            zf = z - d['per_focus']
            zero = zf==0
            rWl2 = np.zeros_like(zf)
            rWl2[~zero] = np.square(z0) / (np.square(z0) + np.square(zf[~zero]))
            rWl2[zero] = 1

            if d['dimension']==2:
                return d['omega0'] * d['a0'] * lon_envelope * np.sqrt( np.sqrt(rWl2) )
            else:
                return d['omega0'] * d['a0'] * lon_envelope * np.sqrt(rWl2)
        elif 't_rise' in d:
            # Calculate fields based on antenna
            length = d['t_rise'] + d['t_flat'] + d['t_fall']
            x = t - d['delay'] - z + z[0]
            inds = [ x<length, x<d['t_rise']+d['t_flat'], x<d['t_rise'], x<0.0 ]

            # Piecewise function done in reverse order of if else to make the last one true
            lon_envelope = np.piecewise( x, inds, [ fenv( (length-x[inds[0]])/d['t_fall'] ), 1.0, 
                                                    fenv(x[inds[2]]/d['t_rise']), 0.0, 0.0] )

            z0 = d['omega0'] * np.square(d['rad_x']) / 2
            zf = z - (d['focus']+z[0])
            zero = zf==0
            rWl2 = np.zeros_like(zf)
            rWl2[~zero] = np.square(z0) / (np.square(z0) + np.square(zf[~zero]))
            rWl2[zero] = 1

            if d['dimension']==2:
                return d['omega0'] * d['a0'] * lon_envelope * np.sqrt( np.sqrt(rWl2) )
            else:
                return d['omega0'] * d['a0'] * lon_envelope * np.sqrt(rWl2)

    def plot_raw(self, file, file_num, ax, fig):
        indices = self.get_indices(file_num)
        if (len(indices) > 1):
            selectors = indices[1:]
        else:
            selectors = None
        dim = len(selectors[:-1])
        if (len(self.get_data(file, file_num)) == 1):
            return
        if (dim == 2):
            self.plot_grid(file, file_num, ax, fig)
        else:
            self.plot_lineout(file, file_num, ax, fig)

    def plot_grid(self, file, file_num, ax, fig):
        try:
            data = self.get_data(file, file_num)
        except:
            data = read_hdf(file.filename).data
        axes = self.get_axes(file_num)
        axis1 = self.construct_axis(file, axes[0], file_num)
        axis2 = self.construct_axis(file, axes[1], file_num)
        if ('operation' in list(self.general_dict.keys())):
            data, axis1, axis2 = analysis(data, self.general_dict['operation'], axes1=axis1, axes2=axis2)
        if ('operation' in list(self.general_dict.keys())):
            axis2 = reflect(axis2, self.general_dict['operation'])
        if ('transpose' in list(self.general_dict.keys())):
            if self.general_dict['operation']:
                axis3 = np.copy(axis1)
                axis1 = np.copy(axis2)
                axis2 = axis3
                data = data.T
        grid_bounds = [axis1[0], axis1[-1], axis2[0], axis2[-1]]

        maximum, minimum = self.get_min_max(file_num)

        if (self.is_log_plot(file_num)):
            if (maximum == 0):
                new_max = 0
            else:
                new_max = maximum / np.abs(maximum) * 10 ** (int(np.log10(np.abs(maximum))) + 1)
            if (minimum == 0):
                new_min = 0
            else:
                new_min = minimum / np.abs(minimum) * 10 ** (int(np.log10(np.abs(minimum))) + 1)

            threshold = self.general_dict['log_threshold'][file_num]
            imAx = ax.imshow(data, aspect=self.general_dict['aspect'][file_num], origin='lower', \
                             interpolation='bilinear', \
                             norm=matplotlib.colors.SymLogNorm(threshold,vmin=new_min,vmax=new_max), \
                             extent=grid_bounds, cmap=self.get_colormap(file_num))
        else:
            if self.get_midpoint(file_num) is None:
                imAx = ax.imshow(data, aspect=self.general_dict['aspect'][file_num], origin='lower', \
                                 interpolation='bilinear', vmin=minimum, vmax=maximum, extent=grid_bounds,
                                 cmap=self.get_colormap(file_num))
            else:
                imAx = ax.imshow(data, aspect=self.general_dict['aspect'][file_num], origin='lower', \
                                 interpolation='bilinear', vmin=minimum, vmax=maximum, extent=grid_bounds,
                                 cmap=self.get_colormap(file_num))
                mid_norm( imAx, self.get_midpoint(file_num) )

        indices = self.get_indices(file_num)
        selectors = indices[1:-1]
        if (indices[0].lower() == 'raw'):
            long_name = self.get_name(file, 'q') + self.append_legend(file_num) + r'$\/$' + self.get_units(file, 'q')
        else:
            long_name = self.get_name(file) + self.append_legend(file_num) + r'$\/$' + self.get_units(file)

        if (self.is_log_plot(file_num)):
            self.add_colorbar(imAx, long_name, self.mod_tickers(minimum, maximum, threshold), file_num, ax, fig)
        else:
            self.add_colorbar(imAx, long_name, None, file_num, ax, fig)

        self.set_labels(ax, file, axes, file_num)

        ax.set_xlim(self.get_x_lims('x1',curr_lims=ax.get_xlim()))
        ax.set_ylim(self.get_x_lims('x2'))

        plt.title(self.general_dict['title'][file_num],fontsize = self.fontsize())

    def plot_contour(self, file1, file2, file_num, ax, fig):
        try:
            data = self.get_data(file2, file_num+1)
        except:
            data = read_hdf(file2.filename).data
        if ('operation' in list(self.general_dict.keys())):
            data = analysis(data, self.general_dict['operation'])
        axes = self.get_axes(file_num)
        axis1 = self.construct_axis(file1, axes[0], file_num)
        axis2 = self.construct_axis(file1, axes[1], file_num)
        if ('operation' in list(self.general_dict.keys())):
            axis2 = reflect(axis2, self.general_dict['operation'])
        grid_bounds = [axis1[0], axis1[-1], axis2[0], axis2[-1]]

        levels = np.linspace(1.5,np.max(data)-0.5,int(np.max(data)+.001)-1)

        rep = np.array([len(axis1)/data.shape[1], len(axis2)/data.shape[0]])

        imAx = ax.contour(np.kron(data, np.ones((rep[1],rep[0]))), levels=levels,
            linewidths=0.5, colors=self.get_colormap(file_num+1), extent=grid_bounds)

    def set_labels(self, ax, file, axes, file_num):
        select = {'left': self.left, 'right': self.right}
        num_on_axis = select[self.general_dict['side'][file_num]]
        plot_type = self.get_indices(file_num)[0]
        if (plot_type == 'lineout'):
            if (num_on_axis == 1):
                ax.set_xlabel(self.axis_label(file, axes[0]), fontsize=self.fontsize())
                ax.set_ylabel(self.get_long_name(file), fontsize=self.fontsize())
            else:
                ax.set_xlabel(self.axis_label(file, axes[0]), fontsize=self.fontsize())
                ax.set_ylabel(self.get_units(file), fontsize=self.fontsize())
        elif (plot_type == 'slice' or plot_type == 'slice_contour'):
            ax.set_xlabel(self.axis_label(file, axes[0], ax_num=0), fontsize=self.fontsize())
            ax.set_ylabel(self.axis_label(file, axes[1], ax_num=1), fontsize=self.fontsize())
        elif (plot_type == 'raw'):
            indices = self.get_indices(file_num)
            selectors = indices[1:-1]
            dim = len(selectors)
            if (dim == 2):
                ax.set_xlabel(self.axis_label(file, axes[0], selectors[1]), fontsize=self.fontsize())
                ax.set_ylabel(self.axis_label(file, axes[1], selectors[0]), fontsize=self.fontsize())
            else:
                if (num_on_axis == 1):
                    label = self.get_long_name(file, 'q')
                    ax.set_xlabel(self.axis_label(file, axes[0], selectors[0]), fontsize=self.fontsize())
                    ax.set_ylabel(label, fontsize=self.fontsize())
                else:
                    ax.set_xlabel(self.axis_label(file, axes[0], selectors[0]), fontsize=self.fontsize())
                    ax.set_ylabel(self.get_units(file, 'q'), fontsize=self.fontsize())
        if ('x_label' in list(self.general_dict.keys())):
            if (self.general_dict['x_label'][file_num] != 'None'):
                ax.set_xlabel(self.general_dict['x_label'][file_num], fontsize=self.fontsize())
        if ('y_label' in list(self.general_dict.keys())):
            if (self.general_dict['y_label'][file_num] != 'None'):
                ax.set_ylabel(self.general_dict['y_label'][file_num], fontsize=self.fontsize())
        ax.tick_params(labelsize=self.fontsize())

    def get_marker(self, file_num):
        if ('markers' in list(self.general_dict.keys()) and file_num < len(self.general_dict['markers'])):
            return self.general_dict['markers'][file_num]
        else:
            return ''

    def get_units(self, file, keyword=None):
        ## assuming osiris notation
        if (keyword == None):
            try:
                data = file[file.attrs['NAME'][0]]
            except:
                try:
                    data = file[list(file)[-1]]
                    try:
                        UNITS = data.attrs['UNITS'][0]
                    except:
                        try:
                            UNITS = file.attrs['UNITS'][0]
                        except:
                            return '[a.u.]'
                    return r'$[{}]$'.format(UNITS.decode('utf-8'))
                except:
                    return '[a.u.]'
        else:
            data = file[keyword]
        try:
            UNITS = data.attrs['UNITS'][0]
        except:
            UNITS = file.attrs['UNITS'][0]
        return r'$[{}]$'.format(UNITS.decode('utf-8'))

    def get_name(self, file, keyword=None):
        ## assuming osiris notation
        if (keyword == None):
            if file.attrs['NAME'][0].decode('utf-8')=="":
                return r'${}$'.format(file.attrs['LABEL'][0].decode('utf-8'))
            else:
                return r'${}$'.format(file.attrs['NAME'][0].decode('utf-8'))
        else:
            try:
                NAME = file[keyword].attrs['LONG_NAME'][0]
                return r'${}$'.format(NAME.decode('utf-8'))
            except:
                return r'${}$'.format(file.attrs['NAME'][0].decode('utf-8'))

    def get_long_name(self, file, keyword=None):
        ## assuming osiris notation
        if (keyword == None):
            try:
                NAME = file.attrs['LABEL'][0]
                UNITS = file.attrs['UNITS'][0]
            except:
                NAME = file[file.attrs['NAME'][0]].attrs['LONG_NAME'][0]
                UNITS = file[file.attrs['NAME'][0]].attrs['UNITS'][0]
        else:
            data = file[keyword]
            try:
                NAME = data.attrs['LONG_NAME'][0]
                UNITS = data.attrs['UNITS'][0]
            except:
                NAME = file.attrs['LABEL'][0]
                UNITS = file.attrs['UNITS'][0]
        return r'${}\/[{}]$'.format(NAME.decode('utf-8'), UNITS.decode('utf-8'))

    def get_axes(self, file_num):
        count, nn = 0, 0
        for num in range(file_num):
            indices = self.get_indices(num)
            typex = indices[0]
            if (typex == 'slice' or typex == 'slice_contour'):
                count += 2
            elif (typex == 'lineout'):
                count += 1
            if (typex == 'raw'):
                count += len(indices[1:]) - 1

        if (self.get_indices(file_num)[0] == 'slice' or self.get_indices(file_num)[0] == 'slice_contour'):
            nn = 2
        elif (self.get_indices(file_num)[0] == 'lineout'):
            nn = 1
        elif (self.get_indices(file_num)[0] == 'raw'):
            nn = len(self.get_indices(file_num)[1:]) - 1
        print(self.general_dict['axes'])
        print(count, count + nn)
        return self.general_dict['axes'][count:(count + nn)]

    def fontsize(self):
        if ('fontsize' in list(self.params.keys())):
            return self.params['fontsize'][0]
        return 16

    def get_colormap(self, file_num):
        if ('colormap' in list(self.general_dict.keys())):
            return self.general_dict['colormap'][file_num]
        else:
            return None

    def get_midpoint(self, file_num, **kwargs):
        if ('midpoint' in list(self.general_dict.keys())):
            return self.general_dict['midpoint'][file_num]
        else:
            return None

    def is_log_plot(self, file_num):
        side = self.general_dict['side'][file_num]
        if (side == 'left'):
            ind = 0
        else:
            ind = 1
        return 'log_threshold' in list(self.general_dict.keys()) and type(self.general_dict['log_threshold'][ind]) is float

    def construct_axis(self, file, label, file_num):
        ## assuming osiris notation
        indices = self.get_indices(file_num)
        selectors = indices[1:]
        if (indices[0] == 'raw'):
            print(file_num, label, selectors[0])
            if (label == selectors[0]):
                return self.raw_edges[file_num][0]
            else:
                return self.raw_edges[file_num][1]
        else:
            h5_data = read_hdf_axes(file.filename)
            ind = size(h5_data.axes)
            for ii in range(size(h5_data.axes)):
                if label == h5_data.axes[ii].attributes['NAME'][0].decode('utf-8'):
                    ind = ii
            axis = [h5_data.axes[ind].axis_min, h5_data.axes[ind].axis_max]
            NX1 = h5_data.shape[len(h5_data.shape)-ind-1]
            return (axis[1] - axis[0]) * np.arange(NX1) / float(NX1) + axis[0]

    def axis_bounds(self, file, label):
        ## assuming osiris notation
        ind, ax = self.select_var(label)
        axis = file['AXIS'][ax][:]
        NX1 = file.attrs['NX'][ind]
        return axis

    def axis_label(self, file, label, keyword=None, ax_num=None):
        ## assuming osiris notation
        if (keyword == None):
            if (ax_num == None):
                ind, ax = self.select_var(label)
                try:
                    data = file['AXIS'][ax]
                except:
                    return label
            else:
                data = file['AXIS/AXIS'+str(ax_num+1)]
        else:
            if (keyword == 'r'):
                return self.axis_label(file, 'x2', 'x2')
            data = file[keyword]
        UNITS = data.attrs['UNITS'][0]
        NAME = data.attrs['LONG_NAME'][0]

        # Check if FFT, for now assume it happens along both directions
        if ('operation' in list(self.general_dict.keys())):
            for op in self.general_dict['operation']:
                if op == 'fft':
                    return r'$k_{}\/[\omega_p/c]$'.format(ax_num+1)

        if UNITS == b'':
            return r'${}$'.format(NAME.decode('utf-8'))
        else:
            return r'${}\/[{}]$'.format(NAME.decode('utf-8'), UNITS.decode('utf-8'))

    def select_var(self, label):
        ind, ax = None, None
        if (label == 'x1'):
            return 0, 'AXIS1'
        elif (label == 'x2'):
            return 1, 'AXIS2'
        else:
            return 2, 'AXIS3'


if __name__ == "__main__":
    main()
