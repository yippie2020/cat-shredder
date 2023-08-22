from direct.distributed import DistributedObjectAI
from direct.task import Task

from otp.ai.AIBase import *
from toontown.boarding import BoardingPartyBase
from toontown.elevators.ElevatorConstants import *

GROUPMEMBER = 0
GROUPINVITE = 1


class DistributedBoardingPartyAI(DistributedObjectAI.DistributedObjectAI, BoardingPartyBase.BoardingPartyBase):
    notify = directNotify.newCategory("DistributedBoardingPartyAI")

    def __init__(self, air, elevatorList, maxSize=4):
        DistributedObjectAI.DistributedObjectAI.__init__(self, air)
        BoardingPartyBase.BoardingPartyBase.__init__(self)
        self.setGroupSize(maxSize)
        self.elevatorIdList = elevatorList
        if __debug__:
            simbase.bp = self
        self.visibleZones = []

    def delete(self):
        self.cleanup()
        DistributedObjectAI.DistributedObjectAI.delete(self)

    def generate(self):
        DistributedObjectAI.DistributedObjectAI.generate(self)
        for elevatorId in self.elevatorIdList:
            elevator = simbase.air.doId2do.get(elevatorId)
            elevator.setBoardingParty(self)

        store = simbase.air.dnaStoreMap.get(self.zoneId)
        if store:
            numVisGroups = store.getNumDNAVisGroupsAI()
            myVisGroup = None
            for index in range(numVisGroups):
                if store.getDNAVisGroupAI(index).getName() == str(self.zoneId):
                    myVisGroup = store.getDNAVisGroupAI(index)

            if myVisGroup:
                numVisibles = myVisGroup.getNumVisibles()
                for index in range(numVisibles):
                    newVisible = myVisGroup.getVisibleName(index)
                    self.visibleZones.append(int(newVisible))
            else:
                self.visibleZones = [self.zoneId]
        else:
            self.visibleZones = [self.zoneId]

    def cleanup(self):
        BoardingPartyBase.BoardingPartyBase.cleanup(self)
        del self.elevatorIdList
        del self.visibleZones

    def getElevatorIdList(self):
        return self.elevatorIdList

    def setElevatorIdList(self, elevatorIdList):
        self.elevatorIdList = elevatorIdList

    def addWacthAvStatus(self, avId):
        """
        tells us when a toon has entered a battle, has changed
        zones or disconnects. Anything that would cause them to
        leave the boardingParty, or keep the boardingParty from
        going to a destination
        """
        self.acceptOnce(self.air.getAvatarExitEvent(avId), self.handleAvatarDisco, extraArgs=[avId])
        self.accept(self.staticGetLogicalZoneChangeEvent(avId), self.handleAvatarZoneChange, extraArgs=[avId])

        messageToonAdded = "Battle adding toon %s" % (avId)
        self.accept(messageToonAdded, self.handleToonJoinedBattle)
        messageToonReleased = "Battle releasing toon %s" % (avId)
        self.accept(messageToonReleased, self.handleToonLeftBattle)

    def handleToonJoinedBattle(self, avId):
        self.notify.debug("handleToonJoinedBattle %s" % (avId))

    def handleToonLeftBattle(self, avId):
        self.notify.debug("handleToonLeftBattle %s" % (avId))

    def removeWacthAvStatus(self, avId):
        self.ignore(self.air.getAvatarExitEvent(avId))
        self.ignore(self.staticGetLogicalZoneChangeEvent(avId))

    def requestInvite(self, inviteeId):
        self.notify.debug("requestInvite %s" % (inviteeId))
        inviterId = self.air.getAvatarIdFromSender()

        invitee = simbase.air.doId2do.get(inviteeId)
        if self.hasActiveGroup(inviteeId):
            reason = BoardingPartyBase.BOARDCODE_DIFF_GROUP
            self.sendUpdateToAvatarId(inviterId, "postInviteNotQualify", [inviteeId, reason, 0])
            self.sendUpdateToAvatarId(inviteeId, "postMessageInvitationFailed", [inviterId])
            return

        if self.hasPendingInvite(inviteeId):
            reason = BoardingPartyBase.BOARDCODE_PENDING_INVITE
            self.sendUpdateToAvatarId(inviterId, "postInviteNotQualify", [inviteeId, reason, 0])
            self.sendUpdateToAvatarId(inviteeId, "postMessageInvitationFailed", [inviterId])
            return

        if self.__isInElevator(inviteeId):
            reason = BoardingPartyBase.BOARDCODE_IN_ELEVATOR
            self.sendUpdateToAvatarId(inviterId, "postInviteNotQualify", [inviteeId, reason, 0])
            self.sendUpdateToAvatarId(inviteeId, "postMessageInvitationFailed", [inviterId])
            return

        if inviterId in self.avIdDict:
            self.notify.debug("old group")
            leaderId = self.avIdDict[inviterId]
            groupList = self.groupListDict.get(leaderId)
            if groupList:
                self.notify.debug("got group list")
                if inviterId == leaderId:
                    if inviteeId in groupList[2]:
                        groupList[2].remove(inviteeId)

                if (len(self.getGroupMemberList(leaderId))) >= self.maxSize:
                    self.sendUpdate("postSizeReject", [leaderId, inviterId, inviteeId])
                elif (not (inviterId in groupList[1])) and (not (inviterId in groupList[2])):
                    if not inviteeId in groupList[1]:
                        groupList[1].append(inviteeId)
                    self.groupListDict[leaderId] = groupList

                    if inviteeId in self.avIdDict:
                        self.notify.warning(
                            "inviter %s tried to invite %s who already exists in the avIdDict." % (inviterId, inviteeId)
                        )
                        self.air.writeServerEvent(
                            "suspicious: inviter",
                            inviterId,
                            " tried to invite %s who already exists in the avIdDict." % inviteeId,
                        )
                    self.avIdDict[inviteeId] = leaderId
                    self.sendUpdateToAvatarId(inviteeId, "postInvite", [leaderId, inviterId])
                    for memberId in groupList[0]:
                        if not (memberId == inviterId):
                            self.sendUpdateToAvatarId(memberId, "postMessageInvited", [inviteeId, inviterId])
                elif inviterId in groupList[2]:
                    self.sendUpdate("postKickReject", [leaderId, inviterId, inviteeId])
        else:
            if inviteeId in self.avIdDict:
                self.notify.warning(
                    "inviter %s tried to invite %s who already exists in avIdDict." % (inviterId, inviteeId)
                )
                self.air.writeServerEvent(
                    "suspicious: inviter",
                    inviterId,
                    " tried to invite %s who already exists in the avIdDict." % inviteeId,
                )

            self.notify.debug("new group")
            leaderId = inviterId
            self.avIdDict[inviterId] = inviterId
            self.avIdDict[inviteeId] = inviterId
            self.groupListDict[leaderId] = [[leaderId], [inviteeId], []]
            self.addWacthAvStatus(leaderId)
            self.sendUpdateToAvatarId(inviteeId, "postInvite", [leaderId, inviterId])

    def requestCancelInvite(self, inviteeId):
        inviterId = self.air.getAvatarIdFromSender()
        if inviterId in self.avIdDict:
            leaderId = self.avIdDict[inviterId]
            groupList = self.groupListDict.get(leaderId)
            if groupList:
                self.removeFromGroup(leaderId, inviteeId)
                self.sendUpdateToAvatarId(inviteeId, "postInviteCanceled", [])

    def requestAcceptInvite(self, leaderId, inviterId):
        inviteeId = self.air.getAvatarIdFromSender()
        self.notify.debug("requestAcceptInvite leader%s inviter%s invitee%s" % (leaderId, inviterId, inviteeId))

        if inviteeId in self.avIdDict:
            if self.hasActiveGroup(inviteeId):
                self.sendUpdateToAvatarId(inviteeId, "postAlreadyInGroup", [])
                return

            if leaderId not in self.avIdDict or not self.isInGroup(inviteeId, leaderId):
                self.sendUpdateToAvatarId(inviteeId, "postSomethingMissing", [])
                return

            memberList = self.getGroupMemberList(leaderId)
            if self.avIdDict[inviteeId]:
                if self.avIdDict[inviteeId] == leaderId:
                    if inviteeId in memberList:
                        self.notify.debug("invitee already in group, aborting requestAcceptInvite")
                        return
                else:
                    self.air.writeServerEvent(
                        "suspicious: ",
                        inviteeId,
                        " accepted a second invite from %s, in %s's group, while he was in alredy in %s's group."
                        % (inviterId, leaderId, self.avIdDict[inviteeId]),
                    )
                    self.removeFromGroup(self.avIdDict[inviteeId], inviteeId, post=0)

            if len(memberList) >= self.maxSize:
                self.removeFromGroup(leaderId, inviteeId)
                self.sendUpdateToAvatarId(
                    inviterId,
                    "postMessageAcceptanceFailed",
                    [inviteeId, BoardingPartyBase.INVITE_ACCEPT_FAIL_GROUP_FULL],
                )
                self.sendUpdateToAvatarId(inviteeId, "postGroupAlreadyFull", [])
                return

            self.sendUpdateToAvatarId(inviterId, "postInviteAccepted", [inviteeId])
            self.addToGroup(leaderId, inviteeId)

        else:
            self.air.writeServerEvent(
                "suspicious: ",
                inviteeId,
                " was invited to %s's group by %s, but the invitee didn't have an entry in the avIdDict."
                % (leaderId, inviterId),
            )

    def requestRejectInvite(self, leaderId, inviterId):
        inviteeId = self.air.getAvatarIdFromSender()
        self.removeFromGroup(leaderId, inviteeId)
        self.sendUpdateToAvatarId(inviterId, "postInviteDelcined", [inviteeId])

    def requestKick(self, kickId):
        leaderId = self.air.getAvatarIdFromSender()
        if kickId in self.avIdDict:
            if self.avIdDict[kickId] == leaderId:
                self.removeFromGroup(leaderId, kickId, kick=1)
                self.sendUpdateToAvatarId(kickId, "postKick", [leaderId])

    def requestLeave(self, leaderId):
        memberId = self.air.getAvatarIdFromSender()
        if memberId in self.avIdDict:
            if leaderId == self.avIdDict[memberId]:
                self.removeFromGroup(leaderId, memberId)

    def checkBoard(self, avId, elevatorId):
        """
        Checks boarding for elevator requirements and paid status.
        """
        elevator = simbase.air.doId2do.get(elevatorId)
        avatar = simbase.air.doId2do.get(avId)
        if avatar:
            if elevator:
                return elevator.checkBoard(avatar)
        return REJECT_BOARDINGPARTY

    def testBoard(self, leaderId, elevatorId, needSpace=0):
        """
        tests boarding against everything, space optional depending on whether
        the leader pressed a goto button, or just got on the elevator
        """
        elevator = None
        boardOkay = BoardingPartyBase.BOARDCODE_MISSING
        avatarsFailingRequirements = []
        avatarsInBattle = []
        if elevatorId in self.elevatorIdList:
            elevator = simbase.air.doId2do.get(elevatorId)
        if elevator:
            if leaderId in self.avIdDict:
                if leaderId == self.avIdDict[leaderId]:
                    boardOkay = BoardingPartyBase.BOARDCODE_OKAY
                    groupSize = len(self.getGroupMemberList(leaderId))
                    if groupSize > self.maxSize:
                        boardOkay = BoardingPartyBase.BOARDCODE_SPACE
                    if needSpace:
                        if groupSize > elevator.countOpenSeats():
                            boardOkay = BoardingPartyBase.BOARDCODE_SPACE

        return (boardOkay, avatarsFailingRequirements, avatarsInBattle)

    def requestBoard(self, elevatorId):
        """
        The group leader has tried to enter the elevator, thereby requesting that
        their group board.
        """
        wantDisableGoButton = False
        leaderId = self.air.getAvatarIdFromSender()
        elevator = None
        if elevatorId in self.elevatorIdList:
            elevator = simbase.air.doId2do.get(elevatorId)
        if elevator:
            if leaderId in self.avIdDict:
                if leaderId == self.avIdDict[leaderId]:
                    group = self.groupListDict.get(leaderId)
                    if group:
                        boardOkay, avatarsFailingRequirements, avatarsInBattle = self.testBoard(
                            leaderId, elevatorId, needSpace=1
                        )
                        if boardOkay == BoardingPartyBase.BOARDCODE_OKAY:
                            leader = simbase.air.doId2do.get(leaderId)
                            if leader:
                                elevator.partyAvatarBoard(leader)
                                wantDisableGoButton = True
                            for avId in group[0]:
                                if not (avId == leaderId):
                                    avatar = simbase.air.doId2do.get(avId)
                                    if avatar:
                                        elevator.partyAvatarBoard(avatar, wantBoardingShow=1)
                            self.air.writeServerEvent(
                                "boarding_elevator", self.zoneId, "%s; Sending avatars %s" % (elevatorId, group[0])
                            )
                        else:
                            self.sendUpdateToAvatarId(
                                leaderId,
                                "postRejectBoard",
                                [elevatorId, boardOkay, avatarsFailingRequirements, avatarsInBattle],
                            )
                            return
        if not wantDisableGoButton:
            self.sendUpdateToAvatarId(
                leaderId, "postRejectBoard", [elevatorId, BoardingPartyBase.BOARDCODE_MISSING, [], []]
            )

    def testGoButtonRequirements(self, leaderId, elevatorId):
        """
        Test if the leader can take his memebers to the elevator destination.
        Return True if everything looks good.
        Send a reject to the leader and return False if somebody doesn't qualify.
        """
        if leaderId in self.avIdDict:
            if leaderId == self.avIdDict[leaderId]:
                if elevatorId in self.elevatorIdList:
                    elevator = simbase.air.doId2do.get(elevatorId)
                    if elevator:
                        boardOkay, avatarsFailingRequirements, avatarsInBattle = self.testBoard(
                            leaderId, elevatorId, needSpace=0
                        )
                        if boardOkay == BoardingPartyBase.BOARDCODE_OKAY:
                            avList = self.getGroupMemberList(leaderId)
                            if 0 in avList:
                                avList.remove(0)
                            if not (leaderId in elevator.seats):
                                return True
                            else:
                                self.notify.warning("avId: %s has hacked his/her client." % leaderId)
                                self.air.writeServerEvent(
                                    "suspicious: ", leaderId, " pressed the GO Button while inside the elevator."
                                )
                        else:
                            self.sendUpdateToAvatarId(
                                leaderId,
                                "rejectGoToRequest",
                                [elevatorId, boardOkay, avatarsFailingRequirements, avatarsInBattle],
                            )
        return False

    def requestGoToFirstTime(self, elevatorId):
        """
        The leader has pushed a GO Button. Do the initial check and respond only to the
        leader if everything is OK.
        """
        callerId = self.air.getAvatarIdFromSender()
        if self.testGoButtonRequirements(callerId, elevatorId):
            self.sendUpdateToAvatarId(callerId, "acceptGoToFirstTime", [elevatorId])

    def requestGoToSecondTime(self, elevatorId):
        """
        The leader has finished his GO Pre Show. Do the initial check and respond to
        all the members of the group to start the GO show.
        """
        callerId = self.air.getAvatarIdFromSender()
        avList = self.getGroupMemberList(callerId)
        if self.testGoButtonRequirements(callerId, elevatorId):
            for avId in avList:
                self.sendUpdateToAvatarId(avId, "acceptGoToSecondTime", [elevatorId])
            THREE_SECONDS = 3.0
            taskMgr.doMethodLater(
                THREE_SECONDS,
                self.sendAvatarsToDestinationTask,
                self.uniqueName("sendAvatarsToDestinationTask"),
                extraArgs=[elevatorId, avList],
                appendTask=True,
            )

    def sendAvatarsToDestinationTask(self, elevatorId, avList, task):
        """
        This is the task that sends the avatars in the Boarding Group to go
        directly to the elevator destinvations after 3 seconds.
        """
        self.notify.debug("entering sendAvatarsToDestinationTask")
        if len(avList):
            if elevatorId in self.elevatorIdList:
                elevator = simbase.air.doId2do.get(elevatorId)
                if elevator:
                    self.notify.warning("Sending avatars %s" % avList)
                    boardOkay, avatarsFailingRequirements, avatarsInBattle = self.testBoard(
                        avList[0], elevatorId, needSpace=0
                    )
                    if not (boardOkay == BoardingPartyBase.BOARDCODE_OKAY):
                        for avId in avatarsFailingRequirements:
                            self.air.writeServerEvent(
                                "suspicious: ", avId, " failed requirements after the second go button request."
                            )
                        for avId in avatarsInBattle:
                            self.air.writeServerEvent(
                                "suspicious: ", avId, " joined battle after the second go button request."
                            )

                    self.air.writeServerEvent(
                        "boarding_go", self.zoneId, "%s; Sending avatars %s" % (elevatorId, avList)
                    )
                    elevator.sendAvatarsToDestination(avList)
        return Task.done

    def handleAvatarDisco(self, avId):
        self.notify.debug("handleAvatarDisco %s" % (avId))
        if avId in self.avIdDict:
            leaderId = self.avIdDict[avId]
            self.removeFromGroup(leaderId, avId)

    def handleAvatarZoneChange(self, avId, zoneNew, zoneOld):
        self.notify.debug("handleAvatarZoneChange %s new%s old%s bp%s" % (avId, zoneNew, zoneOld, self.zoneId))
        if zoneNew in self.visibleZones:
            self.toonInZone(avId)
        elif avId in self.avIdDict:
            leaderId = self.avIdDict[avId]
            self.removeFromGroup(leaderId, avId)

    def toonInZone(self, avId):
        """
        This should never be called, but if an avatar leaves and for some reason is
        still in the boarding system (due to a bug), this tries to put them back in the
        right group
        """
        if avId in self.avIdDict:
            leaderId = self.avIdDict[avId]
            group = self.groupListDict.get(leaderId)
            if leaderId and group:
                self.notify.debug("Calling postGroupInfo from toonInZone")

    def addToGroup(self, leaderId, inviteeId, post=1):
        group = self.groupListDict.get(leaderId)
        if group:
            self.avIdDict[inviteeId] = leaderId
            if inviteeId in group[1]:
                group[1].remove(inviteeId)
            if not (inviteeId in group[0]):
                group[0].append(inviteeId)

            self.groupListDict[leaderId] = group

            if post:
                self.notify.debug("Calling postGroupInfo from addToGroup")
                self.sendUpdate("postGroupInfo", [leaderId, group[0], group[1], group[2]])
            self.addWacthAvStatus(inviteeId)
        else:
            self.sendUpdate("postGroupDissolve", [leaderId, leaderId, [], 0])

    def removeFromGroup(self, leaderId, memberId, kick=0, post=1):
        self.notify.debug("")
        self.notify.debug("removeFromGroup leaderId %s memberId %s" % (leaderId, memberId))
        self.notify.debug("Groups %s" % (self.groupListDict))
        self.notify.debug("avDict %s" % (self.avIdDict))

        if not (leaderId in self.avIdDict):
            self.sendUpdate("postGroupDissolve", [memberId, leaderId, [], kick])
            if memberId in self.avIdDict:
                self.avIdDict.pop(memberId)
            return
        self.removeWacthAvStatus(memberId)
        group = self.groupListDict.get(leaderId)
        if group:
            if memberId in group[0]:
                group[0].remove(memberId)
            if memberId in group[1]:
                group[1].remove(memberId)
            if memberId in group[2]:
                group[2].remove(memberId)

            if kick:
                group[2].append(memberId)
        else:
            return

        if (memberId == leaderId) or (len(group[0]) < 2):
            if leaderId in self.avIdDict:
                self.avIdDict.pop(leaderId)
                for inviteeId in group[1]:
                    if inviteeId in self.avIdDict:
                        self.avIdDict.pop(inviteeId)
                        self.sendUpdateToAvatarId(inviteeId, "postInviteCanceled", [])

            dgroup = self.groupListDict.pop(leaderId)
            for dMemberId in dgroup[0]:
                if dMemberId in self.avIdDict:
                    self.avIdDict.pop(dMemberId)
            self.notify.debug("postGroupDissolve")
            dgroup[0].insert(0, memberId)
            self.sendUpdate("postGroupDissolve", [memberId, leaderId, dgroup[0], kick])
        else:
            self.groupListDict[leaderId] = group
            if post:
                self.notify.debug("Calling postGroupInfo from removeFromGroup")
                self.sendUpdate("postGroupInfo", [leaderId, group[0], group[1], group[2]])

        if memberId in self.avIdDict:
            self.avIdDict.pop(memberId)

        self.notify.debug("Remove from group END")
        self.notify.debug("Groups %s" % (self.groupListDict))
        self.notify.debug("avDict %s" % (self.avIdDict))
        self.notify.debug("")

    def informDestinationInfo(self, offset):
        """
        This function is called from DistributedBoardingParty informing that a
        destination has been changed.
        """
        leaderId = self.air.getAvatarIdFromSender()
        if offset > len(self.elevatorIdList):
            self.air.writeServerEvent(
                "suspicious: ", leaderId, "has requested to go to %s elevator which does not exist" % offset
            )
            return
        memberList = self.getGroupMemberList(leaderId)
        for avId in memberList:
            if avId != leaderId:
                self.sendUpdateToAvatarId(avId, "postDestinationInfo", [offset])

    def __isInElevator(self, avId):
        """
        Returns True if the avatar is found in any elevator in that zone.
        Else returns False.
        """
        inElevator = False
        for elevatorId in self.elevatorIdList:
            elevator = simbase.air.doId2do.get(elevatorId)
            if elevator:
                if avId in elevator.seats:
                    inElevator = True
        return inElevator
