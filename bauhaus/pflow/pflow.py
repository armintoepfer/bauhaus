from collections import OrderedDict, namedtuple
from contextlib import closing, contextmanager
import ninja, os.path as op

Rule           = namedtuple("Rule", ("name", "command"))
BuildStatement = namedtuple("BuildStatement", ("outputs", "rule", "inputs", "variables"))

class IncorrectDuplicateRule(Exception): pass

class ContextTracker(object):
    """
    A class that enables tracking a stack of "context" variables
    """
    def __init__(self):
        self._context = []

    def lookup(self, key):
        for (k, v) in self._context:
            if k == key:
                return v
        else:
            raise KeyError(key)

    def __getitem__(self, key):
        return self.lookup(key)

    def _push(self, key, value):
        self._context.insert(0, (key, value))

    def _pop(self):
        (k, v) = self._context[0]
        del self._context[0]
        return (k, v)

    @contextmanager
    def context(self, key, value):
        """
        RAII method for use with "with" statement
        """
        self._push(key, value)
        yield
        self._pop()

    def contextToDict(self):
        return dict(self._context)


class PFlow(ContextTracker):

    def __init__(self):
        super(PFlow, self).__init__()
        self._rules = OrderedDict()
        self._buildStmts = []

    # ---- rules, build targets  -----

    def formatInContext(self, s):
        if isinstance(s, str):
            return s.format(**self.contextToDict())
        else:
            return s

    def genRuleOnce(self, name, command):
        # Redundant rules get coalesced; error on specifying rules with
        # same name but different content
        if name in self._rules:
            if self._rules[name] != command:
                raise IncorrectDuplicateRule(name)
        else:
            self._rules[name] = command
        return self._rules[name]

    def genBuildStatement(self, outputs, rule, inputs=None, variables=None):
        outputsF = [ self.formatInContext(p) for p in outputs ]
        if inputs is not None:
            inputsF  = [ self.formatInContext(p) for p in inputs ]
        else:
            inputsF = None
        if variables is not None:
            variablesF = { k : self.formatInContext(v)
                           for (k, v) in variables.iteritems() }
        else:
            variablesF = None
        buildStmt = BuildStatement(outputsF, rule, inputsF, variablesF)
        self._buildStmts.append(buildStmt)
        return buildStmt

    def write(self, outputNinjaFname="build.ninja"):
        f = open(outputNinjaFname, "w")
        with closing(ninja.Writer(f)) as w:
            w.comment("Variables")
            w.newline()
            w.variable("ncpus", "8")
            w.variable("grid", "qsub -sync  -cwd -V -b y")
            w.variable("gridSMP", "$grid -pe smp $ncpus")
            w.newline()
            w.comment("Rules")
            w.newline()
            for rule in self._rules.iteritems():
                w.rule(*rule)
                w.newline()
            w.newline()
            w.comment("Build targets")
            for buildStmt in self._buildStmts:
                w.newline()
                w.build(buildStmt.outputs, buildStmt.rule, buildStmt.inputs,
                        variables=buildStmt.variables)
                w.newline()