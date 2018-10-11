simulation
{
	subplots = 6,
	nstart = 0,
	ndump = 1,
	nend = 31,
	sim_dir = '',
	save_dir = 'imag',
	dpi = 300,
	fig_size = 16,9
	fig_layout = 3,2
	fontsize = 12,
}

}

! #1 subplot
data
{
	folders = "MS/FLD/e1",
	title = "Plasma Wave FFT",
	plot_type = "lineout", "x1", "128",
	operation = "fft norm='ortho'", "abs",
	x1_lims = -25, 25,
}

! #2 subplot
data
{
	folders = "MS/FLD/e1",
	title = "Plasma Wave Field",
	colormap = "Jet",
	plot_type = "slice",
	midpoint = 0,
}

! #3 subplot
data
{
	folders = "MS/FLD/e1",
	title = "Plasma Wave On-Axis",
	plot_type = "lineout", "x1", "128",
}

! #4 subplot
data
{
	folders = "MS/FLD/e3",
	title = "Laser Field",
	colormap = "Jet",
	plot_type = "slice",
	midpoint = 0,
}

! #5 subplot
data
{
	folders = "MS/FLD/e3",
	title = "Laser Field On-Axis",
	plot_type = "lineout", "x1", "128",
	operation = "hilbert_env",
}

! #6 subplot
data
{
	folders = "MS/PHA/p1x1/electrons",
	title = "Electron Phasespace",
	log_threshold = 1e-7,
	colormap = "bone_r",
	plot_type = "slice",
	operation = "abs",
}
