# Based on code kindly provided by Adrià González Esteve

import topologic
from topologicpy import DictionaryValueAtKey
import time

from honeybee.model import Model
from honeybee.room import Room
from honeybee.face import Face
from honeybee.shade import Shade
from honeybee.aperture import Aperture
from honeybee.door import Door
from honeybee.boundarycondition import boundary_conditions
import honeybee.facetype
from honeybee.facetype import face_types, Floor, RoofCeiling

from honeybee_energy.constructionset import ConstructionSet
from honeybee_energy.construction.opaque import OpaqueConstruction
from honeybee_energy.construction.window import WindowConstruction
from honeybee_energy.construction.shade import ShadeConstruction
from honeybee_energy.material.opaque import EnergyMaterial
from honeybee_energy.schedule.fixedinterval import ScheduleFixedInterval
from honeybee_energy.schedule.ruleset import ScheduleRuleset
from honeybee_energy.schedule.day import ScheduleDay
from honeybee_energy.load.setpoint import Setpoint
from honeybee_energy.load.hotwater import  ServiceHotWater
from honeybee_energy.ventcool.opening import VentilationOpening
from honeybee_energy.ventcool.control import VentilationControl
from honeybee_energy.ventcool import afn
from honeybee_energy.ventcool.simulation import VentilationSimulationControl
from honeybee_energy.hvac.allair.vav import VAV
from honeybee_energy.hvac.doas.fcu import FCUwithDOAS
from honeybee_energy.hvac.heatcool.windowac import WindowAC

import honeybee_energy.lib.programtypes as prog_type_lib
import honeybee_energy.lib.constructionsets as constr_set_lib

import honeybee_energy.lib.scheduletypelimits as schedule_types
from honeybee_energy.lib.materials import clear_glass, air_gap, roof_membrane, \
    wood, insulation
from honeybee_energy.lib.constructions import generic_exterior_wall, \
    generic_interior_wall, generic_interior_floor, generic_interior_ceiling, \
    generic_double_pane

from honeybee_radiance.modifierset import ModifierSet
from honeybee_radiance.modifier.material import Glass, Plastic, Trans
from honeybee_radiance.dynamic import RadianceShadeState, RadianceSubFaceState, \
    StateGeometry
from honeybee_radiance.sensorgrid import SensorGrid

from ladybug.dt import Time
from ladybug_geometry.geometry3d.pointvector import Point3D, Vector3D
from ladybug_geometry.geometry3d.plane import Plane
from ladybug_geometry.geometry3d.face import Face3D
from ladybug_geometry.geometry3d.polyface import Polyface3D

import os
import json
import random

import math



def getSubTopologies(topology, subTopologyClass):
    subTopologies = []
    if subTopologyClass == topologic.Vertex:
        _ = topology.Vertices(None, subTopologies)
    elif subTopologyClass == topologic.Edge:
        _ = topology.Edges(None, subTopologies)
    elif subTopologyClass == topologic.Wire:
        _ = topology.Wires(None, subTopologies)
    elif subTopologyClass == topologic.Face:
        _ = topology.Faces(None, subTopologies)
    elif subTopologyClass == topologic.Shell:
        _ = topology.Shells(None, subTopologies)
    elif subTopologyClass == topologic.Cell:
        _ = topology.Cells(None, subTopologies)
    elif subTopologyClass == topologic.CellComplex:
        _ = topology.CellComplexes(None, subTopologies)
    return subTopologies

def cellFloor(cell):
    faces = []
    _ = cell.Faces(None, faces)
    c = [x.CenterOfMass().Z() for x in faces]
    return round(min(c),2)

def floorLevels(cells, min_difference):
    floors = [cellFloor(x) for x in cells]
    floors = list(set(floors)) #create a unique list
    floors.sort()
    returnList = []
    for aCell in cells:
        for floorNumber, aFloor in enumerate(floors):
            if abs(cellFloor(aCell) - aFloor) > min_difference:
                continue
            returnList.append("Floor"+str(floorNumber).zfill(2))
            break
    return returnList

def getKeyName(d, keyName):
    keys = d.Keys()
    for key in keys:
        if key.lower() == keyName.lower():
            return key
    return None

def createUniqueName(name, nameList, number):
    if not (name in nameList):
        return name
    elif not ((name+"_"+str(number)) in nameList):
        return name+"_"+str(number)
    else:
        return createUniqueName(name,nameList, number+1)

def processItem(tpBuilding=None,
                tpShadingFacesCluster=None,
                buildingName = "Generic_Building",
                defaultProgramIdentifier = "Generic Office Program",
                defaultConstructionSetIdentifier = "Default Generic Construction Set",
                coolingSetpoint = 25.0,
                heatingSetpoint = 20.0,
                humidifyingSetpoint = 30.0,
                dehumidifyingSetpoint = 55.0,
                roomNameKey = "Name",
                roomTypeKey = "Type"):
    rooms = []
    tpCells = []
    _ = tpBuilding.Cells(None, tpCells)
    # Sort cells by Z Levels
    tpCells.sort(key=lambda c: cellFloor(c), reverse=False)
    fl = floorLevels(tpCells, 2)
    spaceNames = []
    sensorGrids = []
    for spaceNumber, tpCell in enumerate(tpCells):
        tpDictionary = tpCell.GetDictionary()
        tpCellName = None
        tpCellStory = None
        tpCellProgramIdentifier = None
        tpCellConstructionSetIdentifier = None
        tpCellConditioned = True
        if tpDictionary:
            keyName = getKeyName(tpDictionary, 'Story')
            try:
                tpCellStory = DictionaryValueAtKey.processItem([tpDictionary, keyName])
                if tpCellStory:
                    tpCellStory = tpCellStory.replace(" ","_")
            except:
                tpCellStory = fl[spaceNumber]
            if roomNameKey:
                keyName = getKeyName(tpDictionary, roomNameKey)
            else:
                keyName = getKeyName(tpDictionary, 'Name')
            try:
                tpCellName = DictionaryValueAtKey.processItem([tpDictionary,keyName])
                if tpCellName:
                    tpCellName = createUniqueName(tpCellName.replace(" ","_"), spaceNames, 1)
            except:
                tpCellName = tpCellStory+"_SPACE_"+(str(spaceNumber+1))
            if roomTypeKey:
                keyName = getKeyName(tpDictionary, roomTypeKey)
            else:
                keyName = getKeyName(tpDictionary, 'Program')
            try:
                tpCellProgramIdentifier = DictionaryValueAtKey.processItem([tpDictionary, keyName])
                if tpCellProgramIdentifier:
                    program = prog_type_lib.program_type_by_identifier(tpCellProgramIdentifier)
                elif defaultProgramIdentifier:
                    program = prog_type_lib.program_type_by_identifier(defaultProgramIdentifier)
            except:
                program = prog_type_lib.office_program #Default Office Program as a last resort
            keyName = getKeyName(tpDictionary, 'construction_set')
            try:
                tpCellConstructionSetIdentifier = DictionaryValueAtKey.processItem([tpDictionary, keyName])
                if tpCellConstructionSetIdentifier:
                    constr_set = constr_set_lib.construction_set_by_identifier(tpCellConstructionSetIdentifier)
                elif defaultConstructionSetIdentifier:
                    constr_set = constr_set_lib.construction_set_by_identifier(defaultConstructionSetIdentifier)
            except:
                constr_set = constr_set_lib.construction_set_by_identifier("Default Generic Construction Set")
        else:
            tpCellStory = fl[spaceNumber]
            tpCellName = tpCellStory+"_SPACE_"+(str(spaceNumber+1))
            program = prog_type_lib.office_program
            constr_set = constr_set_lib.construction_set_by_identifier("Default Generic Construction Set")
        spaceNames.append(tpCellName)

        tpCellFaces = []
        _ = tpCell.Faces(None, tpCellFaces)
        if tpCellFaces:
            hbRoomFaces = []
            for tpFaceNumber, tpCellFace in enumerate(tpCellFaces):
                tpCellFaceNormal = topologic.FaceUtility.NormalAtParameters(tpCellFace, 0.5, 0.5)
                hbRoomFacePoints = []
                tpFaceVertices = []
                _ = tpCellFace.ExternalBoundary().Vertices(None, tpFaceVertices)
                for tpVertex in tpFaceVertices:
                    hbRoomFacePoints.append(Point3D(tpVertex.X(), tpVertex.Y(), tpVertex.Z()))
                hbRoomFace = Face(tpCellName+'_Face_'+str(tpFaceNumber+1), Face3D(hbRoomFacePoints))
                tpFaceApertures = []
                _ = tpCellFace.Apertures(tpFaceApertures)
                if tpFaceApertures:
                    for tpFaceApertureNumber, tpFaceAperture in enumerate(tpFaceApertures):
                        apertureTopology = topologic.Aperture.Topology(tpFaceAperture)
                        tpFaceApertureDictionary = apertureTopology.GetDictionary()
                        if tpFaceApertureDictionary:
                            tpFaceApertureType = DictionaryValueAtKey.processItem([tpFaceApertureDictionary,'type'])
                        hbFaceAperturePoints = []
                        tpFaceApertureVertices = []
                        _ = apertureTopology.ExternalBoundary().Vertices(None, tpFaceApertureVertices)
                        for tpFaceApertureVertex in tpFaceApertureVertices:
                            hbFaceAperturePoints.append(Point3D(tpFaceApertureVertex.X(), tpFaceApertureVertex.Y(), tpFaceApertureVertex.Z()))
                        if(tpFaceApertureType):
                            if ("door" in tpFaceApertureType.lower()):
                                hbFaceAperture = Door(tpCellName+'_Face_'+str(tpFaceNumber+1)+'_Door_'+str(tpFaceApertureNumber), Face3D(hbFaceAperturePoints))
                            else:
                                hbFaceAperture = Aperture(tpCellName+'_Face_'+str(tpFaceNumber+1)+'_Window_'+str(tpFaceApertureNumber), Face3D(hbFaceAperturePoints))
                        else:
                            hbFaceAperture = Aperture(tpCellName+'_Face_'+str(tpFaceNumber+1)+'_Window_'+str(tpFaceApertureNumber), Face3D(hbFaceAperturePoints))
                        hbRoomFace.add_aperture(hbFaceAperture)
                else:
                    tpFaceDictionary = tpCellFace.GetDictionary()
                    if (abs(tpCellFaceNormal[2]) < 1e-6) and tpFaceDictionary: #It is a mostly vertical wall and has a dictionary
                        apertureRatio = DictionaryValueAtKey.processItem([tpFaceDictionary,'apertureRatio'])
                        if apertureRatio:
                            hbRoomFace.apertures_by_ratio(apertureRatio, tolerance=0.01)
                fType = honeybee.facetype.get_type_from_normal(Vector3D(tpCellFaceNormal[0],tpCellFaceNormal[1],tpCellFaceNormal[2]), roof_angle=30, floor_angle=150)
                hbRoomFace.type = fType
                hbRoomFaces.append(hbRoomFace)
            room = Room(tpCellName, hbRoomFaces, 0.01, 1)
            floor_mesh = room.generate_grid(0.5, 0.5, 1)
            sensorGrids.append(SensorGrid.from_mesh3d(tpCellName+"_SG", floor_mesh))
            heat_setpt = ScheduleRuleset.from_constant_value('Room Heating', heatingSetpoint, schedule_types.temperature)
            cool_setpt = ScheduleRuleset.from_constant_value('Room Cooling', coolingSetpoint, schedule_types.temperature)
            humidify_setpt = ScheduleRuleset.from_constant_value('Room Humidifying', humidifyingSetpoint, schedule_types.humidity)
            dehumidify_setpt = ScheduleRuleset.from_constant_value('Room Dehumidifying', dehumidifyingSetpoint, schedule_types.humidity)
            setpoint = Setpoint('Room Setpoint', heat_setpt, cool_setpt, humidify_setpt, dehumidify_setpt)
            simple_office = ScheduleDay('Simple Weekday', [0, 1, 0], [Time(0, 0), Time(9, 0), Time(17, 0)]) #Todo: Remove hardwired scheduleday
            schedule = ScheduleRuleset('Office Water Use', simple_office, None, schedule_types.fractional) #Todo: Remove hardwired schedule
            shw = ServiceHotWater('Office Hot Water', 0.1, schedule) #Todo: Remove hardwired schedule hot water
            room.properties.energy.program_type = program
            room.properties.energy.construction_set = constr_set
            room.properties.energy.add_default_ideal_air() #Ideal Air Exchange
            room.properties.energy.setpoint = setpoint #Heating/Cooling/Humidifying/Dehumidifying
            room.properties.energy.service_hot_water = shw #Service Hot Water
            if tpCellStory:
                room.story = tpCellStory
            rooms.append(room)
    Room.solve_adjacency(rooms, 0.01)
    #for room in rooms:
        #room.properties.energy.construction_set = constr_set
    #Room.stories_by_floor_height(rooms, min_difference=2.0)

    hbShades = []
    if(tpShadingFacesCluster):
        hbShades = []
        tpShadingFaces = []
        _ = tpShadingFacesCluster.Faces(None, tpShadingFaces)
        for faceIndex, tpShadingFace in enumerate(tpShadingFaces):
            faceVertices = []
            _ = tpShadingFace.ExternalBoundary().Vertices(None, faceVertices)
            facePoints = []
            for aVertex in faceVertices:
                facePoints.append(Point3D(aVertex.X(), aVertex.Y(), aVertex.Z()))
            hbShadingFace = Face3D(facePoints, None, [])
            hbShade = Shade("SHADINGSURFACE_" + str(faceIndex+1), hbShadingFace)
            hbShades.append(hbShade)
    model = Model(buildingName, rooms, orphaned_shades=hbShades)
    model.properties.radiance.sensor_grids = []
    model.properties.radiance.add_sensor_grids(sensorGrids)
    return model

