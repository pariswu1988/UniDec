import os
import sys
import json
import time
import wx
import wx.lib.mixins.listctrl as listmix
import numpy as np
import matplotlib.cm as cm
from matplotlib.pyplot import colormaps
from matplotlib import rcParams
from wx.lib.pubsub import setupkwargs
from wx.lib.pubsub import pub

import multiprocessing
from unidec_modules import UniFit, Extract2D, unidecstructure, PlotAnimations, plot1d, plot2d, miscwindows, \
    MassDefects, nativez, IM_functions
from unidec_modules.PlottingWindow import PlottingWindow
import unidec_modules.unidectools as ud
import h5py
from unidec_modules.hdf5_tools import replace_dataset, get_dataset
from gui_elements.um_list_ctrl import *
import pickle

__author__ = 'michael.marty'

rcParams['ps.useafm'] = True
rcParams['ps.fonttype'] = 42
rcParams['pdf.fonttype'] = 42

extractchoices = {0: "Height", 1: "Local Max", 2: "Area", 3: "Center of Mass", 4: "Local Max Position",
                  5: "Center of Mass 50%", 6: "Center of Mass 10%"}
extractlabels = {0: "Intensity", 1: "Intensity", 2: "Area", 3: "Mass", 4: "Mass", 5: "Mass", 6: "Mass"}

markdict = {u'\u25CB': 'o', u'\u25BD': 'v', u'\u25B3': '^', u'\u25B7': '>', u'\u25A2': 's', u'\u2662': 'd',
            u'\u2606': '*'}
mdkeys = [u'\u25CB', u'\u25BD', u'\u25B3', u'\u25B7', u'\u25A2', u'\u2662', u'\u2606']


# noinspection PyNoneFunctionAssignment,PyNoneFunctionAssignment,PyArgumentList
class DataCollector(wx.Frame):
    def __init__(self, parent, title, config=None, *args, **kwargs):
        wx.Frame.__init__(self, parent, title=title)  # ,size=(200,-1))

        if "directory" in kwargs:
            self.directory = kwargs["directory"]
        else:
            self.directory = ""

        self.config = config

        if self.config is None:
            self.config = unidecstructure.UniDecConfig()
            self.config.initialize()
            self.config.initialize_system_paths()
            print "Using Empty Structure"
            self.config.publicationmode = 1
            if "viridis" in colormaps():
                self.config.cmap = "viridis"
            else:
                self.config.cmap = "jet"

        self.CreateStatusBar(2)
        self.SetStatusWidths([-1, 150])
        pub.subscribe(self.on_motion, 'newxy')

        self.filemenu = wx.Menu()

        self.menuSave = self.filemenu.Append(wx.ID_SAVE, "Save", "Save Parameters")
        self.menuLoad = self.filemenu.Append(wx.ID_ANY, "Load", "Load Parameters")
        self.filemenu.AppendSeparator()

        self.menuSaveFigPNG = self.filemenu.Append(wx.ID_ANY, "Save Figures as PNG",
                                                   "Save all figures as PNG in central directory")
        self.menuSaveFigPDF = self.filemenu.Append(wx.ID_ANY, "Save Figures as PDF",
                                                   "Save all figures as PDF in central directory")

        self.Bind(wx.EVT_MENU, self.on_save, self.menuSave)
        self.Bind(wx.EVT_MENU, self.on_load, self.menuLoad)
        self.Bind(wx.EVT_MENU, self.on_save_fig, self.menuSaveFigPNG)
        self.Bind(wx.EVT_MENU, self.on_save_figPDF, self.menuSaveFigPDF)
        self.toolsmenu = wx.Menu()
        self.menulocalpath = self.toolsmenu.Append(wx.ID_ANY, "Convert to Local Path",
                                                   "Change file name to reflect local path for portability")
        self.Bind(wx.EVT_MENU, self.on_local_path, self.menulocalpath)
        self.menuabsolutepath = self.toolsmenu.Append(wx.ID_ANY, "Convert to Absolute Path",
                                                      "Change file name to reflect absolute path")
        self.Bind(wx.EVT_MENU, self.on_absolute_path, self.menuabsolutepath)
        self.toolsmenu.AppendSeparator()
        self.menuylabel = self.toolsmenu.Append(wx.ID_ANY, "Specify Var. 1 Label", "Adds Var. 1 axis label to plot")
        self.Bind(wx.EVT_MENU, self.on_ylabel, self.menuylabel)
        self.toolsmenu.AppendSeparator()
        self.menuexpfit = self.toolsmenu.Append(wx.ID_ANY, "Exponential Decay Fit",
                                                "Fit all plots to exponential decays")
        self.Bind(wx.EVT_MENU, self.on_exp_fit, self.menuexpfit)
        self.menulinfit = self.toolsmenu.Append(wx.ID_ANY, "Linear Fit",
                                                "Fit all plots to line")
        self.Bind(wx.EVT_MENU, self.on_lin_fit, self.menulinfit)
        self.menusigfit = self.toolsmenu.Append(wx.ID_ANY, "Logistic Fit",
                                                "Fit all plots to logistic equation")
        self.Bind(wx.EVT_MENU, self.on_sig_fit, self.menusigfit)

        self.menuBar = wx.MenuBar()
        self.menuBar.Append(self.filemenu, "&File")
        self.menuBar.Append(self.toolsmenu, "Tools")
        self.SetMenuBar(self.menuBar)

        self.panel = wx.Panel(self)
        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.inputsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.displaysize = wx.GetDisplaySize()
        print self.displaysize
        self.ypanelsizer = wx.BoxSizer(wx.VERTICAL)
        self.ypanel = ListCtrlPanel(self.panel, pres=self, list_type="Y", size=(700, self.displaysize[1] - 300))
        self.ypanel.SetDropTarget(DCDropTarget(self))
        self.ypanelsizer2 = wx.BoxSizer(wx.HORIZONTAL)
        self.addybutton = wx.Button(self.panel, label="Add Files")
        self.Bind(wx.EVT_BUTTON, self.on_add_y, self.addybutton)
        self.ypanelsizer2.Add(self.addybutton, 0, wx.EXPAND)
        self.ypanelsizer2.Add(wx.StaticText(self.panel, label="Directory:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.dirinput = wx.TextCtrl(self.panel, value="", size=(100, 20))
        self.ypanelsizer2.Add(self.dirinput, 1, wx.EXPAND)
        self.dirbutton = wx.Button(self.panel, label="...", size=(20, 20))
        self.Bind(wx.EVT_BUTTON, self.on_choose_dir, self.dirbutton)
        self.ypanelsizer2.Add(self.dirbutton, 0, wx.EXPAND)
        self.ypanelsizer.Add(self.ypanelsizer2, 0, wx.EXPAND)
        self.ypanelsizer.Add(self.ypanel, 0, wx.EXPAND)

        self.xpanel = ListCtrlPanel(self.panel, list_type="X", size=(300, 200))
        self.xpanelsizer = wx.BoxSizer(wx.VERTICAL)
        self.addxbutton = wx.Button(self.panel, label="Add X Value")
        self.Bind(wx.EVT_BUTTON, self.on_add_x, self.addxbutton)
        self.xpanelsizer.Add(self.addxbutton, 0, wx.EXPAND)
        self.xpanelsizer.Add(self.xpanel, 0, wx.EXPAND)

        self.runsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.runsizer.Add(self.xpanelsizer, 0, wx.EXPAND)

        self.runbutton = wx.Button(self.panel, label="Run Extraction", size=(500, 200))
        self.runbutton.SetBackgroundColour((0, 200, 0))
        self.Bind(wx.EVT_BUTTON, self.on_run, self.runbutton)
        self.runsizer.Add(self.runbutton, 0, wx.EXPAND)

        self.ypanelsizer.Add(self.runsizer, 0, wx.EXPAND)

        self.inputsizer.Add(self.ypanelsizer, 0, wx.EXPAND)
        self.sizer.Add(self.inputsizer, 1, wx.EXPAND)

        self.plot1 = plot1d.Plot1d(self.panel)
        self.plot2 = plot1d.Plot1d(self.panel)
        self.plotsizer = wx.BoxSizer(wx.VERTICAL)
        self.plotsizer.Add(self.plot1, 0, wx.EXPAND)
        self.plotsizer.Add(self.plot2, 0, wx.EXPAND)
        self.inputsizer.Add(self.plotsizer, 0, wx.EXPAND)
        self.panel.SetSizer(self.sizer)
        self.sizer.Fit(self)
        self.xvals = []
        self.yvals = []
        self.normflag2 = True
        self.datachoice = 2
        self.window = ''
        self.extractchoice = 0
        self.savename = "collection1.json"
        self.localpath = 0
        self.xcolors = []
        self.data = []
        self.grid = []
        self.var1 = []
        self.xlabel = "Mass"
        self.ylabel = ""
        self.hdf5_file = ""
        self.topname = "ms_dataset"
        self.configname = "config"

        self.update_set(0)
        self.Centre()
        self.Show(True)

        try:
            self.load_x_from_peaks(0)
        except (ValueError, TypeError, AttributeError):
            print "Failed to load from peak list"

        if __name__ == "__main__":
            # testdir = "C:\Python\UniDec\unidec_src\UniDec\\x64\Release"
            try:
                testdir = "Z:\\Group Share\\Deseree\\Ciara\\Test"
                testfile = "collection1.json"
                testdir = "C:\\Data\\Triplicate Data"
                self.load(os.path.join(testdir, testfile))
                pass
            except Exception, e:
                print e
                pass

    def load_x_from_peaks(self, e=None, index=0):
        self.update_get(e)
        try:
            y = self.yvals[index]
            path = y[0]
            if os.path.isfile(path):
                self.hdf5_file = path
                self.hdf = h5py.File(path, 'r')
                pdataset = self.hdf.require_group("/peaks")
                peaks = get_dataset(pdataset, "peakdata")
                indexes = np.arange(0, len(peaks))
                self.xpanel.list.clear_list()
                if not ud.isempty(indexes):
                    for i in indexes:
                        marker = mdkeys[i % len(mdkeys)]
                        self.xpanel.list.add_line(val=i, marker=marker)
        except Exception, ex:
            print "Unable to detect peaks", ex

    def on_save(self, e):
        self.update_get(e)
        # print "Saved: ",self.gridparams
        outdict = {"x": self.xvals, "y": self.yvals, "dir": self.directory}
        dlg = wx.FileDialog(self, "Save Collection in JSON Format", self.directory, self.savename, "*.json", wx.SAVE)
        if dlg.ShowModal() == wx.ID_OK:
            self.savename = dlg.GetPath()
            with open(self.savename, "w") as outfile:
                json.dump(outdict, outfile)
            print "Saved: ", self.savename
        dlg.Destroy()

    def on_load(self, e):
        dlg = wx.FileDialog(self, "Load JSON Collection", self.directory, self.savename, "*.json", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.savename = dlg.GetPath()
            self.load(self.savename)
        dlg.Destroy()

    def load(self, savename):
        with open(savename, "r") as outfile:
            indict = json.load(outfile)
        if "x" in indict:
            self.xvals = indict["x"]
        if "y" in indict:
            self.yvals = indict["y"]
        if "dir" in indict:
            self.directory = indict["dir"]
        self.update_set(0)
        print "Loaded: ", savename
        self.on_run(0)

    def on_add_x(self, e):
        self.update_get()
        index = len(self.xvals)
        print index, self.xvals
        marker = mdkeys[index % len(mdkeys)]
        self.xpanel.list.add_line(val=index, marker=marker)

    def on_add_y(self, e):
        self.update_get(e)
        dlg = wx.FileDialog(self, "Load Files", self.directory, "", "*.hdf5", wx.MULTIPLE)
        if dlg.ShowModal() == wx.ID_OK:
            filenames = dlg.GetPaths()
            for f in filenames:
                self.ypanel.list.add_line(file_name=f)
        dlg.Destroy()
        self.localpath = 0

    def update_get(self, e=None):
        self.xvals = self.xpanel.list.get_list()
        self.yvals = self.ypanel.list.get_list()
        self.directory = self.dirinput.GetValue()

    def update_set(self, e):
        self.dirinput.SetValue(self.directory)
        self.xpanel.list.populate(self.xvals)
        self.ypanel.list.populate(self.yvals)

    def on_exp_fit(self, e=None):
        self.on_run(fit="exp")

    def on_lin_fit(self, e=None):
        self.on_run(fit="lin")

    def on_sig_fit(self, e=None):
        self.on_run(fit="sig")

    def on_run(self, e=None, fit=None):
        tstart = time.clock()
        self.plot1.clear_plot()
        self.plot2.clear_plot()
        self.update_get(e)
        print "Running"
        # print self.yvals
        labels = np.array(self.yvals)[:, 3]
        uniquelabels = np.unique(labels)
        output = []

        if ud.isempty(self.xvals):
            self.xvals = [[u'\u25CB', 0]]
        for x in self.xvals:
            try:
                index = int(x[1])
                marker = markdict[x[0]]
            except:
                print "Error with peak index:", x
                index = 0
                marker = "o"
            for u in uniquelabels:
                extracts = []
                zexts = []
                xvals = []
                for y in self.yvals:
                    label = y[3]
                    if label == u:
                        path = y[0]
                        if self.localpath == 1:
                            path = os.path.join(self.directory, path)
                        color = y[1]
                        linestyle = y[2]
                        print path, u, index, marker, linestyle
                        self.hdf5_file = path
                        self.hdf = h5py.File(path, "r")

                        self.msdata = self.hdf.require_group(self.topname)
                        self.len = self.msdata.attrs["num"]

                        xvals = []
                        zdat = []
                        for f in np.arange(0, self.len):
                            self.msdata = self.hdf.get(self.topname + "/" + str(f))
                            self.attrs = dict(self.msdata.attrs.items())
                            if "var1" in self.attrs.keys():
                                var1 = self.attrs["var1"]
                            elif "collision_voltage" in self.attrs.keys():
                                var1 = self.attrs["collision_voltage"]
                                if self.ylabel == "":
                                    self.ylabel = "Collision Voltage"
                            elif "Collision Voltage" in self.attrs.keys():
                                var1 = self.attrs["Collision Voltage"]
                                if self.ylabel == "":
                                    self.ylabel = "Collision Voltage"
                            else:
                                var1 = f

                            zdata = get_dataset(self.msdata, "charge_data")
                            try:
                                zdata[:, 1] /= np.amax(zdata[:, 1])
                            except:
                                pass
                            zdat.append(ud.center_of_mass(zdata)[0])
                            xvals.append(var1)
                        zexts.append(zdat)

                        pdataset = self.hdf.require_group("/peaks")
                        ex = get_dataset(pdataset, "extracts")[:, index]
                        extracts.append(ex)
                        self.hdf.close()

                if not ud.isempty(xvals) and not ud.isempty(extracts):
                    extracts = np.array(extracts)
                    zexts = np.array(zexts)
                    xvals = np.array(xvals)
                    avg = np.mean(extracts, axis=0)
                    std = np.std(extracts, axis=0)
                    zdat = np.mean(zexts, axis=0)
                    zstd = np.std(zexts, axis=0)
                    lab = u + " " + str(index)
                    fits = []
                    zfits = []

                    if fit is None:
                        if not self.plot1.flag:
                            self.plot1.plotrefreshtop(xvals, avg, "Mass Extracts", self.ylabel, "Mass", None, None,
                                                      nopaint=True, color=color, test_kda=False, linestyle=linestyle)
                        else:
                            self.plot1.plotadd(xvals, avg, color, None, linestyle=linestyle)

                        if not self.plot2.flag:
                            self.plot2.plotrefreshtop(xvals, zdat, "Charge Extracts", self.ylabel, "Charge", None, None,
                                                      nopaint=True, color=color, test_kda=False, linestyle=linestyle)
                        else:
                            self.plot2.plotadd(xvals, zdat, color, None, linestyle=linestyle)
                    else:
                        if fit == "exp":
                            fits, fitdat = ud.exp_fit(xvals, avg)
                            zfits, zfitdat = ud.exp_fit(xvals, zdat)
                        elif fit == "lin":
                            fits, fitdat = ud.lin_fit(xvals, avg)
                            zfits, zfitdat = ud.lin_fit(xvals, zdat)
                        elif fit == "sig":
                            fits, fitdat = ud.sig_fit(xvals, avg)
                            zfits, zfitdat = ud.sig_fit(xvals, zdat)
                        else:
                            print "ERROR: Unsupported fit type"
                            break

                        print "Fits:", fits
                        print "Charge Fits:", zfits

                        if not self.plot1.flag:
                            self.plot1.plotrefreshtop(xvals, fitdat, "Mass Extracts", self.ylabel, "Mass", None, None,
                                                      nopaint=True, color=color, test_kda=False, linestyle=linestyle)
                        else:
                            self.plot1.plotadd(xvals, fitdat, color, None, linestyle=linestyle)

                        if not self.plot2.flag:
                            self.plot2.plotrefreshtop(xvals, zfitdat, "Charge Extracts", self.ylabel, "Charge", None,
                                                      None,
                                                      nopaint=True, color=color, test_kda=False, linestyle=linestyle)
                        else:
                            self.plot2.plotadd(xvals, zfitdat, color, None, linestyle=linestyle)

                        if fit == "sig":
                            self.plot1.addtext("", fits[0], (fits[3]+fits[2]) / 0.95, ymin=fits[3], color=color)
                            self.plot2.addtext("", zfits[0], (zfits[3]+zfits[2]) / 0.95, ymin=zfits[3], color=color)

                    self.plot1.errorbars(xvals, avg, yerr=std, color=color, newlabel=lab, linestyle=" ", marker=marker)

                    self.plot2.errorbars(xvals, zdat, yerr=zstd, color=color, newlabel=lab, linestyle=" ",
                                         marker=marker)
                    out = [[lab], xvals, avg, std, zdat, zstd, fits, zfits]
                    output.append(out)

        output = np.array(output)
        self.data = output
        try:
            hdf = h5py.File(os.path.join(self.directory, "Extracts.hdf5"))
            for l in output:
                dataset = hdf.require_group("/" + l[0][0])
                data = np.array([l[i] for i in xrange(1, 6)])
                fits = l[6]
                zfits = l[7]
                replace_dataset(dataset, "extracts", data)
                if not ud.isempty(fits):
                    replace_dataset(dataset, "fits", fits)
                if not ud.isempty(zfits):
                    replace_dataset(dataset, "zfits", zfits)
            hdf.close()
            # outfile = open(os.path.join(self.directory, "Extracts.pkl"), "wb")
            # pickle.dump(output, outfile)
            # outfile.close()
        except Exception, ex:
            print "Failed to Export Output:", ex

        self.plot1.add_legend()
        self.plot2.add_legend()
        self.plot2.repaint()
        self.plot1.repaint()

    def on_save_fig(self, e):
        "Finished"
        self.update_get(e)
        name1 = os.path.join(self.directory, "Figure1.png")
        if self.plot1.flag:
            self.plot1.on_save_fig(e, name1)
            print name1
        name2 = os.path.join(self.directory, "Figure2.png")
        if self.plot2.flag:
            self.plot2.on_save_fig(e, name2)
            print name2

    def on_save_figPDF(self, e):
        "Finished"
        self.update_get(e)
        name1 = os.path.join(self.directory, "Figure1.pdf")
        if self.plot1.flag:
            self.plot1.on_save_fig(e, name1)
            print name1
        name2 = os.path.join(self.directory, "Figure2.pdf")
        if self.plot2.flag:
            self.plot2.on_save_fig(e, name2)
            print name2

    def on_local_path(self, e):
        "Finished"
        self.update_get(0)
        for i, l in enumerate(self.yvals):
            filename = l[0]
            localpath = os.path.relpath(filename, self.directory)
            l[0] = localpath
        self.update_set(0)
        self.localpath = 1

    def on_absolute_path(self, e):
        "Finished"
        self.update_get(0)
        for i, l in enumerate(self.yvals):
            filename = l[0]
            abspath = os.path.abspath(os.path.join(self.directory, filename))
            l[0] = abspath
        self.update_set(0)
        self.localpath = 0

    def on_ylabel(self, e):
        "Finished"
        dlg = miscwindows.SingleInputDialog(self)
        dlg.initialize_interface(title="Set Variable 1 Label", message="Variable 1 axis label:", defaultvalue="")
        dlg.ShowModal()
        self.ylabel = dlg.value
        print "New  var. 1 axis label:", self.ylabel
        try:
            self.on_run()
        except Exception, ex:
            print "Could not plot extract:", ex
        pass

    def on_choose_dir(self, e):
        'Finished'
        dlg = wx.DirDialog(None, "Choose Top Directory", "", wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.directory = dlg.GetPath()
            self.dirinput.SetValue(self.directory)
            # print self.directory
        dlg.Destroy()

    def on_motion(self, xpos, ypos):
        'Finished'
        if xpos is not None and ypos is not None:
            self.SetStatusText("x=%.4f y=%.2f" % (xpos, ypos), number=1)


# Main App Execution
if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = wx.App(False)
    frame = DataCollector(None, "Ultra Meta Data Collector")
    app.MainLoop()