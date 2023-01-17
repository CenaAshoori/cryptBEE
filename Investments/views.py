from rest_framework.generics import CreateAPIView
from .serializers import *
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated


class BuyCoinView(CreateAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = BuyCoinSerializer(data = request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.create(serializer.validated_data)
        return Response(data, status=status.HTTP_202_ACCEPTED)