import copy
import re
import sys
import ssl
import os, os.path, urllib
import urllib2
from collections import defaultdict

import rdflib
import json
from GlycanResource import GlyTouCan

class GNOme(object):
    version = "1.2.0"
    referenceowl = "https://raw.githubusercontent.com/glygen-glycan-data/GNOme/V%s/GNOme.owl" % (version,)

    referencefmt = 'xml'

    def __init__(self, resource=None, format=None):
        if not resource:
            resource = self.referenceowl
            format = self.referencefmt
        elif not format:
            format = 'xml'
        self.gnome = rdflib.Graph()
        self.gnome.parse(resource, format=format)
        self.ns = dict()
        self.ns['owl'] = rdflib.Namespace('http://www.w3.org/2002/07/owl#')
        self.ns['gno'] = rdflib.Namespace('http://purl.obolibrary.org/obo/GNO_')
        self.ns['rdf'] = rdflib.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#')
        self.ns['rdfs'] = rdflib.Namespace('http://www.w3.org/2000/01/rdf-schema#')
        self.ns[None] = rdflib.Namespace("")

    def triples(self, subj=None, pred=None, obj=None):
        for (s, p, o) in self.gnome.triples(((self.uri(subj) if subj else None), (self.uri(pred) if pred else None),
                                             (self.uri(obj) if obj else None))):
            yield s, p, o

    def uri(self, id):
        if isinstance(id, rdflib.term.URIRef):
            return id
        ns, id = id.split(':', 1)
        if ns in self.ns:
            return self.ns[ns][id]
        return self.ns[None][id]

    def accession(self, uri):
        assert uri.startswith(self.ns['gno'])
        return uri[len(self.ns['gno']):]

    def label(self, uri):
        if isinstance(uri, rdflib.term.URIRef):
            for s, p, o in self.triples(uri, "rdfs:label", None):
                return unicode(o)
        for ns in self.ns.values():
            if ns.startswith('http://') and uri.startswith(ns):
                return uri[len(ns):]
        return unicode(uri)

    def nodes(self):
        for s, p, o in self.triples(None, 'rdf:type', 'owl:Class'):
            acc = self.accession(s)
            if acc == "00000011":
                continue
            yield acc

    def attributes(self, accession):
        uri = "gno:%s" % (accession,)
        attr = dict()

        for s, p, o in self.triples(uri):
            plab = self.label(p)
            if plab != "subClassOf":
                olab = self.label(o)
                attr[plab] = olab
            else:
                olab = self.accession(o)
                if plab not in attr:
		                attr[plab] = []
                attr[plab].append(olab)
        attr[u'level'] = self.level(accession)
        return attr


    def edges(self):
        for n in self.nodes():
            for p in self.parents(n):
                yield p, n

    def root(self):
        return "00000001"

    def parents(self, accession):
        uri = "gno:%s" % (accession,)
        for s, p, o in self.triples(uri, 'rdfs:subClassOf'):
            yield self.accession(o)

    def ancestors(self, accession):
        anc = set()
        for p in self.parents(accession):
            anc.add(p)
            anc.update(self.ancestors(p))
        return anc

    def children(self, accession):
        uri = "gno:%s" % (accession,)
        for s, p, o in self.triples(None, 'rdfs:subClassOf', uri):
            yield self.accession(s)

    def descendants(self, accession):
        desc = set()
        for c in self.children(accession):
            desc.add(c)
            desc.update(self.descendants(c))
        return desc

    def isleaf(self, accession):
        for ch in self.children(accession):
            return False
        return True

    def isroot(self, accession):
        return accession == self.root()

    def level(self, accession):
        uri = "gno:%s" % (accession,)
        for s, p, o in self.triples(uri, "gno:00000021", None):
            return " ".join(unicode(self.label(o)).split()[2:])

    def islevel(self, accession, level):
        return self.level(accession) == level

    def ismolecularweight(self, accession):
        return self.islevel(accession, 'molecular weight')

    def isbasecomposition(self, accession):
        return self.islevel(accession, 'basecomposition')

    def iscomposition(self, accession):
        return self.islevel(accession, 'composition')

    def istopology(self, accession):
        return self.islevel(accession, 'topology')

    def issaccharide(self, accession):
        return self.islevel(accession, 'saccharide')

    def get_basecomposition(self, accession):
        bcomps = set()
        for t in self.ancestors(accession):
            if self.isbasecomposition(t):
                bcomps.add(t)
        exclude = set()
        for t in bcomps:
            if len(self.descendants(t) & bcomps) > 0:
                exclude.add(t)
        for t in exclude:
            bcomps.remove(t)
        assert len(bcomps) <= 1
        if len(bcomps) == 0:
            return None
        return iter(bcomps).next()

    def get_composition(self, accession):
        comps = set()
        for t in self.ancestors(accession):
            if self.iscomposition(t):
                comps.add(t)
        exclude = set()
        for t in comps:
            if len(self.descendants(t) & comps) > 0:
                exclude.add(t)
        for t in exclude:
            comps.remove(t)
        assert len(comps) <= 1
        if len(comps) == 0:
            return None
        return iter(comps).next()

    def get_topology(self, accession):
        topos = set()
        for t in self.ancestors(accession):
            if self.istopology(t):
                topos.add(t)
        exclude = set()
        for t in topos:
            if len(self.descendants(t) & topos) > 0:
                exclude.add(t)
        for t in exclude:
            topos.remove(t)
        assert len(topos) <= 1
        if len(topos) == 0:
            return None
        return iter(topos).next()

    def has_basecomposition(self, accession):
        assert self.isbasecomposition(accession)
	if self.get_basecomposition(accession) == accession:
	    yield accession
        for desc in self.descendants(accession):
	    if self.get_basecomposition(desc) == accession:
		yield desc

    def has_composition(self, accession):
        assert self.iscomposition(accession)
	if self.get_composition(accession) == accession:
	    yield accession
        for desc in self.descendants(accession):
	    if self.get_composition(desc) == accession:
		yield desc

    def has_topology(self, accession):
        assert self.istopology(accession)
	if self.get_topology(accession) == accession:
	    yield accession
        for desc in self.descendants(accession):
	    if self.get_topology(desc) == accession:
		yield desc

    def restrict(self, restriction):
        parents = defaultdict(set)
        keep = set()
        for acc in restriction:
            keep.add(acc)
            for anc in self.ancestors(acc):
                if self.issaccharide(anc):
                    if anc in restriction:
                        parents[acc].add(anc)
                        keep.add(anc)
                else:
                    parents[acc].add(anc)
                    parents[anc].update(self.parents(anc))
                    keep.add(anc)

        toremove = set()
        for n1 in restriction:
            for n2 in parents[n1]:
                for n3 in parents[n2]:
                    if n3 in parents[n1]:
                        toremove.add((n1, n3))
        for n1, n3 in toremove:
            parents[n1].remove(n3)

        for n in self.nodes():
            if n not in keep:
                self.gnome.remove((self.uri("gno:" + n), None, None))
            else:
                self.gnome.remove((self.uri("gno:" + n), self.uri("rdfs:subClassOf"), None))
                for n1 in parents[n]:
                    self.gnome.add((self.uri("gno:" + n), self.uri("rdfs:subClassOf"), self.uri("gno:" + n1)))

    def write(self, handle):
        writer = OWLWriter()
        writer.write(handle, self.gnome)

    def dump(self):
        for acc in sorted(g.nodes()):
            print acc
            for k, v in sorted(g.attributes(acc).items()):
                print "  %s: %s" % (k, v)

    def get_cb_button_str(self, acc):
        for s, p, o in self.triples(None, "gno:00000101", None):
            if acc == self.accession(s):
                return o

    ics2dp = re.compile(r"(\D{3,6})(\d{1,2})")
    def iupac_composition_str_to_dict(self, s):
        res = {}
        for p in self.ics2dp.findall(s):
            res[p[0]] = int(p[1])
        return res

    def get_cbbutton(self, acc):
        return self.iupac_composition_str_to_dict(self.get_cb_button_str(acc))

    def all_cbbutton(self):
        res = {}
        for s, p, o in self.triples(None, "gno:00000101", None):
            acc = self.accession(s)
            res[acc] = self.iupac_composition_str_to_dict(o)
        return res

    def toViewerData(self, output_file_path1, output_file_path2):
        res = {}
        issueList = []

        all_comp = self.all_cbbutton()
        data_composition = {}


        for n in self.nodes():
            t = ""
            if self.issaccharide(n):
                t = "saccharide"
            elif self.istopology(n):
                t = "topology"
            else:
                f1 = self.iscomposition(n)
                f2 = self.isbasecomposition(n)

                if f1 or f2:
                    try:
                        data_composition[n] = {"comp": all_comp[n]}
                    except:
                        print >> sys.stderr, "%s iupac composition is not found" % n
                        issueList.append(n)
                        continue
                    if f1:
                        data_composition[n]["type"] = "composition"
                    else:
                        data_composition[n]["type"] = "basecomposition"
                continue

            try:
                comp = all_comp[n]
            except:
                print >> sys.stderr, "%s iupac composition is not found" % n
                issueList.append(n)
                continue

            per = {}
            per["children"] = list(self.children(n))
            per["type"] = t
            per["comp"] = comp

            res[n] = per

        for n, component in res.items():
            comp = component["comp"]
            t = component["type"]
            if t != "topology":
                continue

            parent = list(self.parents(n))
            topflag = True
            for p in parent:
                try:
                    comp_p = all_comp[p]
                    tors = self.issaccharide(p) or self.istopology(p)
                except:
                    continue

                if not tors:
                    continue

                if comp == comp_p:
                    topflag = False
                    break

            if topflag:
                component["top"] = True

        f = open(output_file_path1, "w")
        f.write(json.dumps(res))
        f.close()

        f2 = open(output_file_path2, "w")
        f2.write(json.dumps(data_composition))
        f2.close()


from alignment import GlycanSubsumption, GlycanEqual
from Monosaccharide import Anomer
import time


class SubsumptionGraph:
    def __init__(self, *args, **kwargs):
        pass

    def compute(self, *args, **kwargs):
        self.gtc = GlyTouCan(usecache=True)
        self.subsumption = GlycanSubsumption()
        self.geq = GlycanEqual()
        self.verbose = kwargs.get('verbose', 0)

        masscluster = defaultdict(dict)
        if len(args) > 0:
	    argmass = set(map(lambda a: str(round(float(a),2)),args))
            for glyacc, mass in self.gtc.allmass():
		rmass = str(round(mass, 2))
                if rmass in argmass:
                    masscluster[rmass][glyacc] = dict(accession=glyacc)
        else:
            for glyacc, mass in self.gtc.allmass():
                rmass = str(round(mass, 2))
                masscluster[rmass][glyacc] = dict(accession=glyacc)
        for rmass, cluster in sorted(masscluster.items(),key=lambda t: float(t[0])):
            self.compute_component(rmass, cluster)

    def warning(self, msg, level):
        if self.verbose >= level:
            print "# WARNING:%d - %s" % (level, msg)
	    sys.stdout.flush()

    def compute_component(self, rmass, cluster):
        start = time.time()

        print "# START %s - %d accessions in molecular weight cluster for %s" % (time.ctime(), len(cluster), rmass)
        sys.stdout.flush()

        badparse = 0
        total = len(cluster)
        allgly = dict()
        for acc in sorted(cluster):
            gly = self.gtc.getGlycan(acc)
            if not gly:
                badparse += 1
                skels = self.gtc.getUnsupportedSkeletonCodes(acc)
                if len(skels) > 0:
                    for skel in skels:
                        self.warning("unsupported skeleton code: " + skel + " in glycan " + acc, 2)
                else:
                    self.warning("unknown problem parsing glycan " + acc, 2)
                continue
            cluster[acc]['glycan'] = gly
            cluster[acc]['mass'] = self.gtc.getmass(acc)

        clusteracc = set(map(lambda t: t[0], filter(lambda t: t[1].has_key('glycan'), cluster.items())))

        outedges = defaultdict(set)
        inedges = defaultdict(set)

	self.warning("Computation of subsumption relationships started",5)
        for acc1 in sorted(clusteracc):
            gly1 = cluster[acc1]['glycan']
            for acc2 in sorted(clusteracc):
                gly2 = cluster[acc2]['glycan']
                if acc1 != acc2:
		    self.warning("%s <?= %s"%(acc1,acc2),5)
                    if self.subsumption.leq(gly1, gly2):
                        if not self.geq.eq(gly1, gly2) or acc2 < acc1:
                            outedges[acc2].add(acc1)
                            inedges[acc1].add(acc2)
	self.warning("Computation of subsumption relationships done",5)

        for acc in sorted(clusteracc):
            topo = self.gtc.gettopo(acc)
            if topo:
                if topo not in cluster:
                    self.warning("annotated topology %s of %s is not in %s rounded mass cluster" % (topo, acc, rmass),
                                 1)
                elif not cluster[topo].get('glycan'):
                    self.warning("annotated topology %s of %s cannot be parsed" % (topo, acc), 1)
                elif acc not in outedges[topo] and acc != topo:
                    self.warning("annotated topology %s does not subsume %s" % (topo, acc), 1)
            comp = self.gtc.getcomp(acc)
            if comp:
                if comp not in cluster:
                    self.warning(
                        "annotated composition %s of %s is not in %s rounded mass cluster" % (comp, acc, rmass), 1)
                elif not cluster[comp].get('glycan'):
                    self.warning("annotated composition %s of %s cannot be parsed" % (comp, acc), 1)
                elif acc not in outedges[comp] and acc != comp:
                    self.warning("annotated composition %s does not subsume %s" % (comp, acc), 1)
            bcomp = self.gtc.getbasecomp(acc)
            if bcomp:
                if bcomp not in cluster:
                    self.warning(
                        "annotated base composition %s of %s is not in %s rounded mass cluster" % (bcomp, acc, rmass),
                        1)
                elif not cluster[bcomp].get('glycan'):
                    self.warning("annotated base composition %s of %s cannot be parsed" % (bcomp, acc), 1)
                elif acc not in outedges[bcomp] and acc != bcomp:
                    self.warning("annotated base composition %s does not subsume %s" % (bcomp, acc), 1)
            try:
                umw = cluster[acc]['glycan'].underivitized_molecular_weight()
            except LookupError:
                umw = None
            if umw == None:
                self.warning("mass could not be computed for %s" % (acc), 2)
            elif abs(cluster[acc]['mass'] - umw) > 0.0001:
                self.warning(
                    "annotated mass %s for %s is different than computed mass %s" % (cluster[acc]['mass'], acc, umw), 1)

        for acc in sorted(clusteracc):

            if acc == self.gtc.getbasecomp(acc):
                cluster[acc]['level'] = "BaseComposition"
                cluster[acc]['bcomp'] = acc
            elif acc == self.gtc.getcomp(acc):
                cluster[acc]['level'] = "Composition"
                if self.gtc.getbasecomp(acc):
                    cluster[acc]['bcomp'] = self.gtc.getbasecomp(acc)
                cluster[acc]['comp'] = acc
            elif acc == self.gtc.gettopo(acc):
                cluster[acc]['level'] = "Topology"
                if self.gtc.getbasecomp(acc):
                    cluster[acc]['bcomp'] = self.gtc.getbasecomp(acc)
                if self.gtc.getcomp(acc):
                    cluster[acc]['comp'] = self.gtc.getcomp(acc)
                cluster[acc]['topo'] = acc
            else:
                if self.gtc.gettopo(acc):
                    cluster[acc]['level'] = "Saccharide"
                    cluster[acc]['topo'] = self.gtc.gettopo(acc)
                    if self.gtc.getbasecomp(acc):
                        cluster[acc]['bcomp'] = self.gtc.getbasecomp(acc)
                    if self.gtc.getcomp(acc):
                        cluster[acc]['comp'] = self.gtc.getcomp(acc)

        for acc in sorted(clusteracc):
            gly = cluster[acc]['glycan']
            level = cluster[acc].get('level')
            if self.any_anomer(gly):
                if not level:
                    cluster[acc]['level'] = 'Saccharide*'
                elif level != "Saccharide":
                    self.warning(
                        "annotation inferred level %s for %s != computed level Saccharide (anomer)" % (level, acc), 1)
		    # cluster[acc]['level'] = 'Saccharide*'
                continue
            if self.any_parent_pos(gly):
                if not level:
                    cluster[acc]['level'] = 'Saccharide*'
                elif level != "Saccharide":
                    self.warning(
                        "annotation inferred level %s for %s != computed level Saccharide (parent_pos)" % (level, acc),
                        1)
                    # cluster[acc]['level'] = 'Saccharide*'
                continue
            if self.any_links(gly):
                if not level:
                    cluster[acc]['level'] = 'Topology*'
                elif level != "Topology":
                    self.warning("annotation inferred level %s for %s != computed level Topology" % (level, acc), 1)
                    # cluster[acc]['level'] = 'Topology*'
                continue
            if self.mono_count(gly) == 1 and self.any_ring(gly):
                if not level:
                    cluster[acc]['level'] = 'Topology*'
                elif level != "Topology":
                    self.warning("annotation inferred level %s for %s != computed level Topology" % (level, acc), 1)
                    # cluster[acc]['level'] = 'Topology*'
                continue
	    if self.any_ring(gly):
                self.warning("%s has no linkages but does have ring values" % (acc,), 1)
            if self.any_stem(gly):
                if not level:
                    cluster[acc]['level'] = 'Composition*'
                elif level != "Composition":
                    self.warning("annotation inferred level %s for %s != computed level Composition" % (level, acc), 1)
                    # cluster[acc]['level'] = 'Composition*'
                continue
            if not level:
                cluster[acc]['level'] = 'BaseComposition*'
            elif level != "BaseComposition":
                self.warning("annotation inferred level %s for %s != computed level BaseComposition" % (level, acc), 1)
                # cluster[acc]['level'] = 'BaseComposition*'

        for acc in sorted(clusteracc):
            g = cluster[acc]
            if not g.get('topo'):
                if g.get('level') in ("Topology", "Topology*"):
                    g['topo'] = acc + "*"
                else:
                    for acc1 in inedges[acc]:
                        if cluster[acc1].get('level') in ("Topology", "Topology*"):
                            if not g.get('topo') or g.get('topo').rstrip("*") in inedges[acc1]:
                                g['topo'] = acc1 + "*"
            if not g.get('comp'):
                if g.get('level') in ("Composition", "Composition*"):
                    g['comp'] = acc + "*"
                else:
                    for acc1 in inedges[acc]:
                        if cluster[acc1].get('level') in ("Composition", "Composition*"):
                            if not g.get('comp') or g.get('comp').rstrip("*") in inedges[acc1]:
                                g['comp'] = acc1 + "*"
            if not g.get('bcomp'):
                if g.get('level') in ("BaseComposition", "BaseComposition*"):
                    g['bcomp'] = acc + "*"
                else:
                    for acc1 in inedges[acc]:
                        if cluster[acc1].get('level') in ("BaseComposition", "BaseComposition*"):
                            if not g.get('bcomp') or g.get('bcomp').rstrip("*") in inedges[acc1]:
                                g['bcomp'] = acc1 + "*"
        if len(clusteracc) < 1:
            print "# DONE - Elapsed time %.2f sec." % (time.time() - start,)
            sys.stdout.flush()
            return

        print "# NODES - %d/%d glycans in molecular weight cluster for %s" % (len(clusteracc), total, rmass)
        for acc in sorted(clusteracc, key=lambda acc: (cluster[acc].get('level'),acc) ):
            g = cluster[acc]
            print acc, g.get('mass'), g.get('level'), g.get('topo'), g.get('comp'), g.get('bcomp'),
            gly = g.get('glycan')
	    extras = []
	    if not gly.has_root():
		extras.append("COMP")
	    if gly.undetermined() and gly.has_root():
	        extras.append("UNDET")
	    if gly.fully_determined():
		extras.append("FULL")
	    for m,c in sorted(gly.iupac_composition(floating_substituents=False,aggregate_basecomposition=True).items()):
                if m != "Count" and c > 0:
		    extras.append("%s:%d"%(m,c))
	    print " ".join(extras)
        print "# ENDNODES - %d/%d glycans in molecular weight cluster for %s" % (len(clusteracc), total, rmass)
        sys.stdout.flush()

        prunedoutedges = self.prune_edges(outedges)
        prunedinedges = self.prune_edges(inedges)

        print "# TREE"
        for r in sorted(clusteracc):
            if len(prunedinedges[r]) == 0:
                self.print_tree(cluster, prunedoutedges, r)
        print "# ENDTREE"

        print "# EDGES"
        for n in sorted(clusteracc):
            print "%s:" % (n,),
            print " ".join(sorted(prunedoutedges[n]))
        print "# ENDEDGES"
        sys.stdout.flush()

        print "# DONE - Elapsed time %.2f sec." % (time.time() - start,)
        sys.stdout.flush()

    def any_anomer(self, gly):
        for m in gly.all_nodes():
            if m.anomer() in (Anomer.alpha, Anomer.beta):
                return True
        return False

    def any_parent_pos(self, gly):
        for l in gly.all_links():
            if l.parent_pos() != None and l.parent_pos() != set([l.parent().ring_start()]):
                return True
        return False

    def any_ring(self, gly):
        for m in gly.all_nodes():
            if m.ring_start() or m.ring_end():
                return True
        return False

    def any_links(self, gly):
        for l in gly.all_links():
            return True
        return False

    def any_stem(self, gly):
        for m in gly.all_nodes():
            if m.stem():
                return True
        return False

    def mono_count(self, gly):
        return sum(1 for _ in gly.all_nodes())

    def prune_edges(self, inedges):
        edges = copy.deepcopy(inedges)
        toremove = set()
        for n1 in list(edges):
            for n2 in edges[n1]:
                for n3 in edges[n2]:
                    assert n3 in edges[n1], ", ".join([n1, n2, n3, ":"] + list(edges[n1]) + [":"] + list(edges[n2]))
                    if n3 in edges[n1]:
                        toremove.add((n1, n3))
        for n1, n3 in toremove:
            edges[n1].remove(n3)
        return edges

    def print_tree(self, cluster, edges, root, indent=0):
        print "%s%s" % (" " * indent, root), cluster[root]['level']
        for ch in sorted(edges[root]):
            self.print_tree(cluster, edges, ch, indent + 2)


    # Dump file parsing part starts here
    raw_data = {}
    dumpfilepath = ""
    warnings = defaultdict(set)
    warningsbytype = None
    monosaccharide_count = {}
    monosaccharide_count_pattern = re.compile(r"\w{3,8}:\d{1,2}")

    def loaddata(self, dumpfilepath):
        self.readfile(dumpfilepath)
        self.dumpfilepath = dumpfilepath
        for index in range(len(self.errorcategory)):
            self.errorcategory[index][1] = re.compile(self.errorcategory[index][1])

    def readfile(self, dumpfilepath):
        f = open(dumpfilepath)
        raw_data = {}
        for l in f:
            l = l.strip()

            if l.startswith("#"):
                if l.startswith("# WARNING"):
                    t1, msg = l.split(" - ")
                    temp1 = re.compile(r"\d").findall(t1)
                    if len(temp1) != 1:
                        raise RuntimeError
                    level = temp1[0]
                    self.warnings[level].add(msg)
                    continue

                lineInfo = "node"  # node type none
                if l.startswith("# NODES"):
                    lineInfo = "node"
                    mass = float(re.compile("\d{2,5}\.\d{1,2}").findall(l)[0])
                    mass = "%.2f" % mass
                    content = {"nodes": {}, "edges": {}}
                    raw_data[mass] = content
                elif l.startswith("# EDGES"):
                    lineInfo = "edge"
                else:
                    lineInfo = "none"
            else:

                if lineInfo == "none":
                    continue
                elif lineInfo == "node":
                    nodeacc = l.split()[0]
		    nodemw = "%.2f"%(float(l.split()[1]),)
                    nodetype = l.split()[2].rstrip("*")
                    topoacc = l.split()[3].rstrip("*")
		    if topoacc == "None":
			topoacc = None
                    compacc = l.split()[4].rstrip("*")
		    if compacc == "None":
			compacc = None
                    bcompacc = l.split()[5].rstrip("*")
		    if bcompacc == "None":
			bcompacc = None
                    content["nodes"][nodeacc] = (nodemw,nodetype,topoacc,compacc,bcompacc)

                    mono_count = {}
                    for cell in l.split():
                        temp2 = self.monosaccharide_count_pattern.findall(cell)
                        if len(temp2) == 1:
                            temp2 = temp2[0].split(":")
                            iupac_comp_mono, count = temp2[0], int(temp2[1])
                            mono_count[iupac_comp_mono] = count
                        if mono_count:
                            temp3 = ""
                            for iupac_mono_str, mono_count_eatch in sorted(mono_count.items()):
                                temp3 += iupac_mono_str + str(mono_count_eatch)
                            self.monosaccharide_count[nodeacc] = mono_count

                elif lineInfo == "edge":
                    to = re.compile("G\d{5}\w{2}").findall(l)
                    fromx = to.pop(0)
                    if to:
                        content["edges"][fromx] = to
                else:
                    raise RuntimeError
        self.raw_data = raw_data

        self.allnodestype = {}
        self.alledges = {}
        for component in raw_data.values():
            self.allnodestype.update(copy.deepcopy(component["nodes"]))
            self.alledges.update(copy.deepcopy(component["edges"]))

        allmass = list()
        for m in self.raw_data.keys():
            self.allnodestype[m] =  (m, "molecular weight", None, None, None)
            allmass.append(m)
            top = set(raw_data[m]["nodes"].keys())
            for chilren in raw_data[m]["edges"].values():
                top = top - set(chilren)
            top = list(top)
            self.alledges[m] = top

        self.allnodestype["00000001"] = "glycan"
        self.alledges["00000001"] = allmass

	self.allinedges = defaultdict(set)
	for pa,chs in self.alledges.items():
	    for ch in chs:
		self.allinedges[ch].add(pa)

        return raw_data

    def root(self):
        return "00000001"

    def nodes(self):
        for n in self.allnodestype.keys():
            yield n

    def edges(self):
        for n in self.nodes():
            if n in self.alledges:
                for c in self.alledges[n]:
                    yield (n, c)

    def parents(self, accession):
        for p in self.allinedges.get(accession, []):
            yield p

    def ancestors(self, accession):
        anc = set()
        for p in self.parents(accession):
            anc.add(p)
            anc.update(self.ancestors(p))
        return anc

    def children(self, accession):
        for c in self.alledges.get(accession, []):
            yield c

    def descendants(self, accession):
        desc = set()
        for c in self.children(accession):
            desc.add(c)
            desc.update(self.descendants(c))
        return desc

    def isleaf(self, accession):
        for ch in self.children(accession):
            return False
        return True

    def isroot(self, accession):
        return accession == self.root()

    def level(self, accession):
	if accession in self.allnodestype:
	    return self.allnodestype[accession][1].lower()
        return None

    def islevel(self, accession, level):
        return self.level(accession) == level

    def ismolecularweight(self, accession):
        return self.islevel(accession, 'molecular weight')

    def isbasecomposition(self, accession):
        return self.islevel(accession, 'basecomposition')

    def iscomposition(self, accession):
        return self.islevel(accession, 'composition')

    def istopology(self, accession):
        return self.islevel(accession, 'topology')

    def issaccharide(self, accession):
        return self.islevel(accession, 'saccharide')

    def get_molecularweight(self, accession):
	if accession in self.allnodestype:
	    return self.allnodestype[accession][0]
	return None

    def get_basecomposition(self, accession):
	if accession in self.allnodestype:
	    bcomp = self.allnodestype[accession][4]
	    if bcomp and bcomp in self.allnodestype:
	        return bcomp
	return None

    def get_composition(self, accession):
	if accession in self.allnodestype:
	    comp = self.allnodestype[accession][3]
	    if comp and comp in self.allnodestype:
	        return comp
	return None

    def get_topology(self, accession):
	if accession in self.allnodestype:
	    topo = self.allnodestype[accession][2]
	    if topo and topo in self.allnodestype:
	        return topo
	return None

    def get_iupac_composition(self, accession):
        return self.monosaccharide_count.get(accession, None)

    def get_iupac_composition_for_viewer(self, accession):
        mono_count = self.get_iupac_composition(accession)
        if not mono_count:
            return None

        res = {}
        for m in ['GlcNAc', 'GalNAc', 'ManNAc', 'Glc', 'Gal', 'Man', 'Fuc', 'NeuAc', 'NeuGc', "Hex", "HexNAc"]:
            if m in mono_count:
                res[m] = mono_count[m]

        xxx = 0
        for m in mono_count.keys():
            if m not in ['GlcNAc', 'GalNAc', 'ManNAc', 'Glc', 'Gal', 'Man', 'Fuc', 'NeuAc', 'NeuGc', "Hex", "HexNAc"]:
                if m in ['Pent', 'HexA', 'HexN', "Xxx"]:
                    xxx += mono_count[m]
        if xxx > 0:
            res["Xxx"] = xxx
        return res

    def get_iupac_composition_str_for_viewer(self, accession):
        s = ""
        d = self.get_iupac_composition_for_viewer(accession)
        for iupac in sorted(d.keys()):
            s += iupac+str(d[iupac])
        return s

    def has_basecomposition(self, accession):
        assert self.isbasecomposition(accession), accession
	if self.get_basecomposition(accession) == accession:
	    yield accession
	for desc in self.descendants(accession):
	    if self.get_basecomposition(desc) == accession:
		yield desc

    def has_composition(self, accession):
        assert self.iscomposition(accession), accession
	if self.get_composition(accession) == accession:
	    yield accession
        for desc in self.descendants(accession):
	    if self.get_composition(desc) == accession:
		yield desc

    def has_topology(self, accession):
        assert self.istopology(accession), accession
	if self.get_topology(accession) == accession:
	    yield accession
	for desc in self.descendants(accession):
	    if self.get_topology(desc) == accession:
		yield desc

    def regexget(self, p, s):
        searchres = list(p.finditer(s))
        if len(searchres) == 1:
            return searchres[0].groupdict()["ans"]
        else:
            return None

    errorcategory = [
        ["cannot_parse_glycan_at_upper_subsumption",
         r"annotated (topology|composition|base composition) (?P<ans>(G\d{5}\w{2})) of G\d{5}\w{2} cannot be parsed"],
        ["cannot_parse_glycan_unknown", r"unknown problem parsing glycan (?P<ans>(G\d{5}\w{2}))"],
        ["unsupported_skeleton_code", r"unsupported skeleton code: (?P<ans>(.{1,10})) in glycan G\d{5}\w{2}"],
        ["mass_cannot_be_computed", r"mass could not be computed for (?P<ans>(G\d{5}\w{2}))"],
        ["mass_inconsistency",
         r"annotated mass \d*\.\d* for (?P<ans>(G\d{5}\w{2})) is different than computed mass \d*\.\d*"],
        # ["", r""],
    ]

    def geterrortype(self, s):
        for errortype, p in self.errorcategory:
            res0 = self.regexget(p, s)
            if res0:
                return errortype, res0
        return None, s

    def getwarningsbytype(self):
        if self.warningsbytype:
            return self.warningsbytype

        res = defaultdict(set)

        for i in reduce(lambda x, y: list(set(list(x) + list(y))), self.warnings.values()):
            errortype, ans = self.geterrortype(i)
            res[errortype].add(ans)

        self.warningsbytype = res
        return res

    def warningbytypetotal(self):
        warnings = self.getwarningsbytype()
        temp = map(lambda x: len(x), warnings.values())
        return reduce(lambda x, y: x + y, temp)

    def generateOWL(self, input_file_path, output_file_path, mass_lut_file_path, version=None):
        self.loaddata(input_file_path)

        r = OWLWriter(mass_LUT_file_path=mass_lut_file_path, version=version)

        for mass in self.nodes():
            if not self.ismolecularweight(mass):
                continue
            mass = "%.2f" % float(mass)

            nodes = self.descendants(mass)

            r.addNode(mass, nodetype="molecularweight")

            for n in nodes:
                # molecular weight has a space between two words
                r.addNode(n, nodetype=self.level(n))
                node_obj = r.getNode(n)
                node_obj.set_basecomposition(self.get_basecomposition(n))
                node_obj.set_composition(self.get_composition(n))
                node_obj.set_topology(self.get_topology(n))
                node_obj.set_iupac_composition(self.get_iupac_composition_str_for_viewer(n))


            nodes.add(mass)

            for n in nodes:
                if self.children(n):
                    for c in self.children(n):
                        r.connect(r.getNode(n), r.getNode(c), "subsumes")

        f = open(output_file_path, "w")
        s = r.write(f, r.make_graph())
        f.close()




from rdflib import URIRef, Namespace


class OWLWriter():
    _nodes = {}

    def __init__(self, mass_LUT_file_path=None, version=None):
        self.version = version
        if mass_LUT_file_path:
            self.mass_LUT_file_path = mass_LUT_file_path
        else:
            self.mass_LUT_file_path = "./mass_lut.txt"
        self.readmassidmap(mass_LUT_file_path)


    def addNode(self, nodeID, nodetype=None):
        self._nodes[nodeID] = NormalNode(nodeID, nodetype=nodetype)

    def addNodes(self, nodes):
        for nodeID in nodes:
            if nodeID not in self._nodes:
                self.addNode(nodeID)
            else:
                raise Exception

    def connect(self, n1, n2, edgeType):
        n1.connect(n2, edgeType)

    def getNode(self, nodeID):
        return self._nodes[nodeID]

    def allRelationship(self):
        res = set()
        for n in self._nodes.values():
            for r in n.getLink():
                res.add(r)
        res = list(res)
        return res

    def readmassidmap(self, mass_LUT_file_path):
        d = {}
        if mass_LUT_file_path:
            mass_lut_file_content = open(mass_LUT_file_path).read().strip().split("\n")
            for e, i in enumerate(mass_lut_file_content):
                if e == 0:
                    continue
                x = i.split("\t")
                d[float(x[1])] = x[0]
        else:
            d[1.01] = "10000001"
        self.massiddict = d

    newMass = False

    def overwritemasslookuptable(self):
        print "new mass ID was assigned"
        mass_lut_file_handle = open(self.mass_LUT_file_path, "w")
        mass_lut_file_handle.write("id\tmass\n")
        for mass in sorted(self.massiddict.keys()):
            id = self.massiddict[mass]
            mass_lut_file_handle.write("%s\t%.2f\n" % (id, mass))
        mass_lut_file_handle.close()

    gno = "http://purl.obolibrary.org/obo/"
    gtcs = "http://glytoucan.org/Structures/Glycans/"
    iao = "http://purl.obolibrary.org/obo/"
    gtco = "http://www.glytoucan.org/glyco/owl/glytoucan#"
    rocs = "http://www.glycoinfo.org/glyco/owl/relation#"

    glycan_class = 1
    definition_class = "IAO_0000115"
    subsumption_level_class = 11
    subsumption_level_annotation_property = 21
    glytoucan_id_annotation_property = 22
    glytoucan_link_annotation_property = 23

    cbbutton_annotation_property = 101

    subsumption_level = {

        "molecularweight": {"id": 12,
                            "label": "subsumption category molecular weight",
                            "definition": """
                                A subsumption category for glycans
                                described by their underivatized
                                molecular weight.
					  """,
                            "seeAlso": ["gtco:has_derivatization_type",
                                        "gtco:derivatization_type",
                                        "gtco:derivatization_type_permethylated"],
                            "comment": """
                                Underivatized molecular weight: The
                                molecular weight in the absence of any
                                chemical manipulation of a glycan for
                                analytical purposes. A common glycan
                                derivitization (chemical manipulation)
                                that affects glycan molecular weight
                                is permethylation.
                                       """
                            },

        "basecomposition": {"id": 13,
                            "label": "subsumption category basecomposition",
                            "definition": """
				A subsumption category for glycans
				described by the number and type of
				monosaccharides with no monosaccharide
				stereochemistry or glycosidic bonds
				linking monosaccharides indicated.
					  """,
                            "seeAlso": ["rocs:Base_composition"]
                            },

        "composition": {"id": 14,
                        "label": "subsumption category composition",
                        "definition": """
				A subsumption category for glycans
				described by the number and type
				of monosaccharides with partial or
				complete monosaccharide stereochemistry,
				but with no glycosidic bonds linking
				monosaccharides indicated.
					  """,
                        "seeAlso": ["rocs:Monosaccharide_composition"]
                        },

        "topology": {"id": 15,
                     "label": "subsumption category topology",
                     "definition": """
				A subsumption category for glycans
				described by the arrangement of
				monosaccharides and the glycosidic bonds
				linking them, but with no linkage position
				or anomeric configuration indicated.
					  """,
                     "seeAlso": ["rocs:Glycosidic_topology"]
                     },

        "saccharide": {"id": 16,
                       "label": "subsumption category saccharide",
                       "definition": """
                                A subsumption category for glycans
                                described by the arrangement of
                                monosaccharides and the glycosidic
                                bonds linking them, and with partial or
                                complete linkage position or anomeric
                                configuration indicated.
					  """,
                       "seeAlso": ["rocs:Linkage_defined_saccharide"]
                       },

    }

    has_subsumption_level = {

        "basecomposition": {
            "id": 33,
            "label": "has_basecomposition",
            "definition": """A metadata relation between a glycan and a glycan, with subsumption level basecomposition, that is equivalent to the glycan after the removal of all glycosidic bonds linking its monosaccharides and all monosaccharide stereochemistry information."""
        },

        "composition": {
            "id": 34,
            "label": "has_composition",
            "definition": """A metadata relation between a glycan and a glycan, with subsumption level composition, that is equivalent to the glycan after the removal of all glycosidic bonds linking its monosaccharides."""
        },

        "topology": {
            "id": 35,
            "label": "has_topology",
            "definition": """A metadata relation between a glycan and a glycan, with subsumption level topology, that is equivalent to the glycan after the removal of all linkage positions and anomeric configurations."""
        }
    }

    def gnoid(self, id):
        try:
            id = int(id)
            return "GNO_%08d" % (id,)
        except:
            pass
        assert re.search('^G[0-9]{5}[A-Z]{2}$', id)
        return "GNO_" + id

    def gnouri(self, id):
        return rdflib.URIRef(self.gno + self.gnoid(id))

    def make_graph(self):

        outputGraph = rdflib.Graph()

        rdf = rdflib.RDF
        rdfs = rdflib.RDFS
        owl = rdflib.OWL
        dc = rdflib.namespace.DC

        Literal = rdflib.Literal

        gno = Namespace(self.gno)
        gtcs = Namespace(self.gtcs)
        iao = Namespace(self.iao)
        gtco = Namespace(self.gtco)
        rocs = Namespace(self.rocs)

        outputGraph.bind("owl", owl)
        outputGraph.bind("gno", gno)
        outputGraph.bind("obo", iao)
        outputGraph.bind("dc", dc)
        outputGraph.bind("rocs", rocs)

        root = rdflib.URIRef("http://purl.obolibrary.org/obo/gno.owl")

        # Add ontology
        outputGraph.add((root, rdf.type, owl.Ontology))

        # VersionIRI
        if self.version:
            outputGraph.add(
                (root, owl.versionIRI, URIRef("http://purl.obolibrary.org/obo/gno/%s/GNOme.owl" % self.version))
            )

        # Copyright
        outputGraph.add(
            (root, dc.license, URIRef("http://creativecommons.org/licenses/by/4.0/")))
        outputGraph.add((root, rdfs.comment, Literal(
            "Glycan Naming Ontology is licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).")))
        outputGraph.add((root, rdfs.comment, Literal(" ".join("""
               Glycan Naming Ontology is licensed under CC BY 4.0. You
               are free to share (copy and redistribute the material
               in any medium or format) and adapt (remix, transform,
               and build upon the material) for any purpose, even
               commercially. for any purpose, even commercially. The
               licensor cannot revoke these freedoms as long as you follow
               the license terms. You must give appropriate credit (by
               using the original ontology IRI for the whole ontology and
               original term IRIs for individual terms), provide a link
               to the license, and indicate if any changes were made. You
               may do so in any reasonable manner, but not in any way
               that suggests the licensor endorses you or your use.
        """.split()))))

        # Add AnnotationProperty for definition
        definition = iao[self.definition_class]
        outputGraph.add((definition, rdf.type, owl.AnnotationProperty))
        outputGraph.add((definition, rdfs.isDefinedBy, iao["iao.owl"]))
        outputGraph.add((definition, rdfs.label, Literal("definition")))

        # Add AnnotationProperty for subsumption level
        has_subsumption_level_node = self.gnouri(self.subsumption_level_annotation_property)

        outputGraph.add((has_subsumption_level_node, rdf.type, owl.AnnotationProperty))
        outputGraph.add(
            (has_subsumption_level_node, rdfs.label, Literal("has_subsumption_category")))
        outputGraph.add((has_subsumption_level_node, definition,
                         Literal("A metadata relation between a glycan and its subsumption category.")))

        # Add AnnotationProperty for linking Glytoucan
        has_glytoucan_id_node = self.gnouri(self.glytoucan_id_annotation_property)

        outputGraph.add((has_glytoucan_id_node, rdf.type, owl.AnnotationProperty))
        outputGraph.add((has_glytoucan_id_node, rdfs.label, Literal("has_glytoucan_id")))
        outputGraph.add((has_glytoucan_id_node, definition,
                         Literal("The accession of the GlyTouCan entry describing the indicated glycan.")))

        has_glytoucan_link_node = self.gnouri(self.glytoucan_link_annotation_property)

        outputGraph.add((has_glytoucan_link_node, rdf.type, owl.AnnotationProperty))
        outputGraph.add((has_glytoucan_link_node, rdfs.label, Literal("has_glytoucan_link")))
        outputGraph.add((has_glytoucan_link_node, definition,
                         Literal("The URL of the GlyTouCan entry describing the indicated glycan.")))

        # Add sumbsumption level class and its instances
        rdfNodeSubsumption = self.gnouri(self.subsumption_level_class)

        outputGraph.add((rdfNodeSubsumption, rdf.type, owl.Class))
        outputGraph.add((rdfNodeSubsumption, rdfs.label, Literal("subsumption category")))
        outputGraph.add((rdfNodeSubsumption, definition,
                         Literal("Extent of glycan characterization provided by a glycan description.")))

        subsumptionLevel = {}

        for level in ("molecularweight", "basecomposition", "composition", "topology", "saccharide"):
            details = self.subsumption_level[level]
            rdfNode = self.gnouri(details["id"])
            subsumptionLevel[level] = rdfNode
            outputGraph.add((rdfNode, rdf.type, owl.NamedIndividual))
            outputGraph.add((rdfNode, rdf.type, rdfNodeSubsumption))
            outputGraph.add((rdfNode, rdfs.label, Literal(details["label"])))
            outputGraph.add((rdfNode, definition, Literal(" ".join(details["definition"].split()))))
            if "comment" in details:
                outputGraph.add((rdfNode, rdfs.comment, Literal(" ".join(details["comment"].split()))))
            for sa in details.get('seeAlso', []):
                ns, term = sa.split(":")
                outputGraph.add((rdfNode, rdfs.seeAlso, eval("%s.%s" % (ns, term))))

        # Add AnnotationProperty for 3 different has subsumption level
        has_xxx_nodes = {}
        for sl in ("basecomposition", "composition", "topology"):
            has_xxx_node = self.gnouri(self.has_subsumption_level[sl]["id"])

            outputGraph.add((has_xxx_node, rdf.type, owl.AnnotationProperty))
            outputGraph.add((has_xxx_node, rdfs.label, Literal(self.has_subsumption_level[sl]["label"])))
            outputGraph.add((has_xxx_node, definition, Literal(self.has_subsumption_level[sl]["definition"])))

            has_xxx_nodes[sl] = has_xxx_node

        has_topology_node = has_xxx_nodes["topology"]
        has_composition_node = has_xxx_nodes["composition"]
        has_basecomposition_node = has_xxx_nodes["basecomposition"]

        # Add AnnotationProperty for IUPAC composition (for the viewer)
        cbbutton_node = self.gnouri(self.cbbutton_annotation_property)

        outputGraph.add((cbbutton_node, rdf.type, owl.AnnotationProperty))
        outputGraph.add((cbbutton_node, rdfs.label, Literal("CB button")))


        # Glycan class under OWL things
        rdfNode = self.gnouri(self.glycan_class)

        outputGraph.add((rdfNode, rdf.type, owl.Class))
        outputGraph.add((rdfNode, rdfs.label, Literal("glycan")))
        outputGraph.add((rdfNode, definition,
                         Literal("A compound consisting of monosaccharides linked by glycosidic bonds.")))
        outputGraph.add((rdfNode, rdfs.seeAlso,
                         rdflib.URIRef("http://purl.obolibrary.org/obo/CHEBI_50699")))
        outputGraph.add((rdfNode, rdfs.seeAlso,
                         rdflib.URIRef("http://purl.obolibrary.org/obo/CHEBI_18154")))

        for n in self._nodes.values():
            if n._nodeType != "molecularweight":
                rdfNode = self.gnouri(n.getID())
            else:
                try:
                    id = self.massiddict[float(n.getID())]
                except KeyError:
                    mass = n.getID()
                    id = str(int(max(self.massiddict.values())) + 1)
                    self.massiddict[float(mass)] = id
                    self.newMass = True
                rdfNode = self.gnouri(id)
            outputGraph.add((rdfNode, rdf.type, owl.Class))

            if n._nodeType:
                # outputGraph.add((rdfNode, rdfs.label, ns2[n._nodeType]))
                outputGraph.add((rdfNode, has_subsumption_level_node, subsumptionLevel[n._nodeType.lower()]))
            else:
                raise ValueError

            if n._nodeType != "molecularweight":
                outputGraph.add((rdfNode, has_glytoucan_id_node, Literal(n.getID())))
                outputGraph.add((rdfNode, has_glytoucan_link_node, gtcs[n.getID()]))
            else:
                outputGraph.add((rdfNode, rdfs.subClassOf, self.gnouri(self.glycan_class)))
                outputGraph.add((rdfNode, rdfs.label,
                                 Literal("glycan of molecular weight %s Da." % n.getID())))
                outputGraph.add((rdfNode, definition,
                                 Literal(
                                     "A glycan characterized by underivitized molecular weight of %s Daltons" % n.getID())))

            bcomp_acc = n.get_basecomposition()
            comp_acc = n.get_composition()
            topo_acc = n.get_topology()
            if bcomp_acc:
                outputGraph.add((rdfNode, has_basecomposition_node, self.gnouri(bcomp_acc)))
            if comp_acc:
                outputGraph.add((rdfNode, has_composition_node, self.gnouri(comp_acc)))
            if topo_acc:
                outputGraph.add((rdfNode, has_topology_node, self.gnouri(topo_acc)))

            cbbutton_str = n.get_iupac_composition()
            if cbbutton_str:
                outputGraph.add((rdfNode, cbbutton_node, Literal(cbbutton_str)))




        for l in self.allRelationship():
            if l.getEdgeType() == "subsumes":
                if l._sideA._nodeType == "molecularweight":
                    id = self.massiddict[float(l._sideA.getID())]
                    n1 = self.gnouri(id)
                else:
                    n1 = self.gnouri(l._sideA.getID())
                n2 = self.gnouri(l._sideB.getID())
                outputGraph.add((n2, rdfs.subClassOf, n1))

        if self.newMass:
            self.overwritemasslookuptable()

        return outputGraph

    def write(self, handle, graph):
        from rdflib.plugins.serializers.rdfxml import PrettyXMLSerializer
        writer = PrettyXMLSerializer(SubjectOrderedGraph(graph), max_depth=1)
        writer.serialize(handle)


# Defined solely to manipulate the accessor methods used by
# rdflib.plugins.serializers.rdfxml.PrettyXMLSerializer so that subjects
# and predictates are output in a deterministic order, and without nesting.

class SubjectOrderedGraph(object):

    def __init__(self, graph):
        self.graph = graph
        self.namespace_manager = self.graph.namespace_manager
        self.subjects_callno = 0
        self.subjects_order = {'gno.owl': 0, 'IAO_0000115': 1}

    def sortkey(self, *args):
        return tuple(map(str, args))

    def subject_sortkey(self, node):
        strnode = str(node)
        item = strnode.rsplit('/', 1)[1]
        return (self.subjects_order.get(item, 2), strnode)

    def subjects(self, *args, **kwargs):
        self.subjects_callno += 1
        if self.subjects_callno > 1:
            for n in sorted(self.graph.subjects(*args, **kwargs),
                            key=self.subject_sortkey):
                yield n

    def predicate_objects(self, *args, **kwargs):
        for p, o in sorted(self.graph.predicate_objects(*args, **kwargs),
                           key=lambda t: self.sortkey(*t)):
            yield p, o

    def objects(self, *args, **kwargs):
        for o in sorted(self.graph.objects(*args, **kwargs),
                        key=self.sortkey, reverse=True):
            yield o

    def __contains__(self, *args, **kwargs):
        return self.graph.__contains__(*args, **kwargs)

    def predicates(self, *args, **kwargs):
        return self.graph.predicates(*args, **kwargs)

    def triples_choices(self, *args, **kwargs):
        return self.graph.triples_choices(*args, **kwargs)



class NormalNode:
    _id = None
    _nodeType = None
    _nodeTypes = tuple(["saccharide", "topology", "composition", "basecomposition", "molecularweight"])

    def __init__(self, id, nodetype=None):
        self._links = []
        self._id = id
        self._nodeType = nodetype

    def __str__(self):
        return self._id

    def getID(self):
        return self._id

    def getLink(self):
        return self._links

    def connect(self, node, edgeType=None):
        l = NormalLink(self, node, edgeType)

    def disconnect(self, node, edgeType=None):
        for l in self._links:
            if self in l.getBothNodes() and node in l.getBothNodes():  # and edgeType == l.getEdgeType:
                l.delete()

    def getparent(self):
        res = []
        for l in self._links:
            if l.getEdgeType() == "subsumes" and l._sideB == self:
                res.append(l.getoppositenode(self))
        return res

    def getchild(self):
        res = []
        for l in self._links:
            if l.getEdgeType() == "subsumes" and l._sideA == self:
                res.append(l.getoppositenode(self))
        return res

    def getequavalent(self):
        res = []
        for l in self._links:
            if l.getEdgeType() == "equal":
                res.append(l.getoppositenode(self))
        return res

    def getdirectlylinkednodes(self):
        res = []
        for l in self._links:
            res.append(l.getoppositenode(self))
        return res

    def set_basecomposition(self, bc):
        self._basecomposition = bc

    def get_basecomposition(self):
        try:
            return self._basecomposition
        except AttributeError:
            return None

    def set_composition(self, c):
        self._composition = c

    def get_composition(self):
        try:
            return self._composition
        except AttributeError:
            return None

    def set_topology(self, topology):
        self._topology = topology

    def get_topology(self):
        try:
            return self._topology
        except AttributeError:
            return None

    def set_iupac_composition(self, ic):
        self._iupac_composition_str = ic

    def get_iupac_composition(self):
        try:
            return self._iupac_composition_str
        except AttributeError:
            return None



class NormalLink:
    _id = None
    _edgeType = None
    _edgeTypes = tuple(["equal", "subsumes"])
    _exist = False
    # Real node object rather than node ID
    _sideA = None  # Parent
    _sideB = None  # Child

    def __init__(self, n1, n2, et):
        self._exist = True
        self._sideA = n1
        self._sideB = n2
        self._edgeType = et
        n1.getLink().append(self)
        n2.getLink().append(self)

    def __str__(self):
        return "%s -- %s --> %s" % (self._sideA.getID(), self._edgeType, self._sideB.getID())

    def getEdgeType(self):
        return self._edgeType

    def getBothNodes(self):
        return [self._sideA, self._sideB]

    def getoppositenode(self, nodeOBJ):
        if nodeOBJ == self._sideA:
            return self._sideB
        elif nodeOBJ == self._sideB:
            return self._sideA
        else:
            raise IndexError

    def delete(self):
        self._sideA.getLink().remove(self)
        self._sideB.getLink().remove(self)


if __name__ == "__main__":
    cmd = sys.argv[1]
    sys.argv.pop(1)

    if cmd == "restrict":

        restriction = set(open(sys.argv[1]).read().split())

        g = GNOme()
        g.restrict(restriction)
        g.write(sys.stdout)

    elif cmd == "dump":

        g = GNOme()
        g.dump()

    elif cmd == "compute":

        verbose = 0
        while len(sys.argv) > 1 and sys.argv[1] == "-v":
            verbose += 1
            sys.argv.pop(1)

        g = SubsumptionGraph()
        g.compute(*sys.argv[1:], verbose=verbose)

    elif cmd == "writeowl":
        # python GNOme.py writeowl ../smw/glycandata/data/gnome_subsumption_raw.txt ./GNOme.owl mass_lookup_2decimal v1.1.5

        # "../smw/glycandata/data/gnome_subsumption_raw.txt"

        versionTag = None
        if len(sys.argv) < 4:
            print "Please provide dumpfile, output file path(with file name), mass LUT path and version (optional)"
            sys.exit(1)
        if len(sys.argv) > 4:
            versionTag = sys.argv[4]

        ifn = sys.argv[1]  # path to input file
        ofn = sys.argv[2]
        mass_lut = sys.argv[3]

        subsumption_instance = SubsumptionGraph()
        subsumption_instance.generateOWL(ifn, ofn, mass_lut, version=versionTag)

    elif cmd == "writeresowl":

        if len(sys.argv) < 4:
            print "Please provide GNOme.owl, restriction set name, output file path"
            sys.exit(1)

        ifn = sys.argv[1]
        ofn = sys.argv[3]
        restriction_accs_file = sys.argv[2]

        accs = open(restriction_accs_file).read().strip().split()

        GNOme_res = GNOme(resource=ifn)
        GNOme_res.restrict(accs)

        f = open(ofn, "w")
        GNOme_res.write(f)
        f.close()

    elif cmd == "viewerdata":
        # python GNOme.py viewerdata ./GNOme.owl ./gnome_subsumption_raw.txt ./GNOme.browser.js

        if len(sys.argv) < 4:
            print "Please provide GNOme.owl and output file path"
            sys.exit(1)

        ifn = sys.argv[1]
        ofn_data = sys.argv[2]
        ofn_comp = sys.argv[3]
        gnome = GNOme(resource=ifn)
        gnome.toViewerData(ofn_data, ofn_comp)

    elif cmd == "UpdateAcc":

        if len(sys.argv) < 4:
            print "Please provide restriction set name and file path"
            sys.exit(1)

        restriction_set_name = sys.argv[1]
        fp = sys.argv[2]

        restriction_set = []
        if restriction_set_name == "BCSDB":
            sys.exit(0)

        elif restriction_set_name == "GlyGen":
            fp = os.path.dirname(os.path.abspath(__file__)) + "/../smw/glycandata/data/glygen_accessions.txt"
            restriction_set = open(fp).read().strip().split()

        elif restriction_set_name == "GlycanData":
            glycandata_tsv_fp = "../smw/glycandata/export/allglycan.tsv"

            restriction_set = open(glycandata_tsv_fp).read().strip().split()
            restriction_set.pop(0)
        else:
            print "Restriction set: %s is not supported"
            sys.exit(1)

        open(fp, "w").write("\n".join(restriction_set))

        json_fp = open(sys.argv[3], "w")
        json.dump(restriction_set, json_fp)


    else:
        print >> sys.stderr, "Bad command: %s" % (cmd,)
        sys.exit(1)
